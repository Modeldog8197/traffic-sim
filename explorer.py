"""Finite reproducible search, separate tuning, frozen held-out evaluation."""
import itertools
import json
import math
import random
import time
from pathlib import Path
from .models import Scenario, ExperimentSpec
from .network import DATA, describe, net_path
from .demand import manifest
from .engine import execute
from .comparison import canonical_hash, compare
from .frames import atomic_json
from .store import connect, task, update_task, update_job
from .statistics import estimate, nondominated

METRICS = ['mean', 'delay', 'p95', 'full_demand_loss', 'person_loss', 'completion_rate', 'bus_mean', 'co2_kg', 'queue_seconds', 'od_inequality', 'invalid', 'unfinished']

def parameter_patch(s, key, value, info):
    if key.startswith('junction:'):
        jid = key.split(':', 1)[1]
        phases = next(j['phases'] for j in info['junctions'] if j['id'] == jid)
        s['signals'][jid] = {str(p['index']): value for p in phases if p['editable']}
    elif key.startswith('speed:') or key.startswith('access:'):
        eid = key.split(':', 1)[1]
        road = next(r for r in info['roads'] if r['id'] == eid)
        edit = s['roads'].setdefault(eid, {'closed': False, 'speed': road['speed'], 'allowed': ['passenger', 'bus']})
        if key.startswith('speed:'): edit['speed'] = value
        else:
            edit['closed'] = value == 'closed'
            edit['allowed'] = ['bus'] if value == 'bus_only' else ['passenger', 'bus']
    else:
        s[key] = value

def plan(spec):
    info = describe(spec.scenario.network)
    space = spec.space
    dimensions = []
    for key, values in [('green', space.greens), ('controller', space.controllers), ('transit_extension', space.transit_extensions)]:
        if values: dimensions.append((key, sorted(set(values))))
    for prefix, values in [('junction:', space.junction_greens), ('speed:', space.road_speeds), ('access:', space.road_access)]:
        for key, options in sorted(values.items()):
            if not options: raise ValueError(f'{key} has an empty search range.')
            if prefix == 'junction:' and not any(j['id'] == key and j['signal'] for j in info['junctions']): raise ValueError('Unknown signal in search space.')
            if prefix != 'junction:' and not any(r['id'] == key for r in info['roads']): raise ValueError('Unknown road in search space.')
            dimensions.append((prefix + key, sorted(set(options))))
    total = math.prod(len(v) for _, v in dimensions)
    if total > 1_000_000: raise ValueError('Search space exceeds one million combinations. Reduce permitted ranges.')
    indices = list(range(total)) if total <= spec.max_candidates else sorted(random.Random(spec.search_seed).sample(range(total), spec.max_candidates))
    base = spec.scenario.model_dump(mode='json')
    candidates = [{'id': 'baseline', 'scenario': base, 'changes': {}, 'label': 'Baseline'}]
    seen = {canonical_hash({k: v for k, v in base.items() if k != 'name'})}
    for n in indices:
        values = []
        remaining = n
        for key, options in reversed(dimensions):
            values.append((key, options[remaining % len(options)]))
            remaining //= len(options)
        draft = json.loads(json.dumps(base))
        for key, value in reversed(values): parameter_patch(draft, key, value, info)
        hashed = canonical_hash({k: v for k, v in draft.items() if k != 'name'})
        if hashed in seen: continue
        seen.add(hashed)
        cid = hashed[:10]
        changes = {key: value for key, value in values if key not in base or base.get(key) != value}
        draft['name'] = 'Candidate ' + cid[:4]
        Scenario(**draft)
        candidates.append({'id': cid, 'scenario': draft, 'changes': changes, 'label': draft['name']})
    finalists = min(spec.finalists, len(candidates) - 1)
    frozen_max = 1 + finalists + (2 * finalists if spec.ablations else 0)
    runs = len(candidates) * len(spec.search_seeds) + (1 + finalists) * len(spec.tuning_seeds) + frozen_max * len(spec.conditions) * len(spec.evaluation_seeds)
    if runs > spec.budget: raise ValueError(f'Conservative budget is {runs} simulations; selected cap is {spec.budget}. Increase cap or reduce candidates, conditions, finalists or seeds.')
    return {'schema_version': 2, 'network_version': info['version'], 'space_size': total, 'candidate_count': len(candidates), 'candidates': candidates, 'maximum_runs': runs, 'method': 'Exhaustive finite grid' if total <= spec.max_candidates else 'Seeded uniform sample without replacement from a finite grid', 'stages': {'search': len(candidates) * len(spec.search_seeds), 'tuning': (1 + finalists) * len(spec.tuning_seeds), 'evaluation_max': frozen_max * len(spec.conditions) * len(spec.evaluation_seeds)}, 'note': 'Ablations reserve up to two additional frozen variants per finalist; identical variants are deduplicated.'}

def condition(s, name, spec, seed):
    value = json.loads(json.dumps(s))
    value['seed'] = seed
    if name in ('uniform', 'peak'): value['pattern'] = name
    if name == 'high_demand': value['demand'] = min(2000, round(value['demand'] * 1.5))
    if name == 'bus_mix':
        value['bus_fraction'] = min(.5, value['bus_fraction'] + .15)
        for line in value.get('transit', []):
            line['headway'] = max(15, round(line['headway'] * .7))
            line['departures'] = []
    if name == 'disruption':
        road = next(r for r in describe(value['network'])['roads'] if r['id'] == spec.disruption_road)
        edit = value['roads'].setdefault(road['id'], {'speed': road['speed'], 'allowed': ['passenger', 'bus']})
        edit['closed'] = True
    value['network_version'] = describe(value['network'])['version']
    return Scenario(**value)

def summarize_candidates(candidates, records, spec, stage):
    rows = []
    for c in candidates:
        entries = [r for r in records if r['stage'] == stage and r['candidate'] == c['id']]
        if not entries: continue
        # Average the tested conditions within each seed before overall uncertainty.
        seeds = sorted({r['seed'] for r in entries})
        def per_seed(key):
            values = []
            for seed in seeds:
                v = [r['metrics'].get(key) for r in entries if r['seed'] == seed]
                if v and all(x is not None for x in v): values.append(sum(v) / len(v))
            return values
        metrics = {key: estimate(per_seed(key)) for key in METRICS}
        failures = []
        for r in entries:
            b = next((x for x in records if x['stage'] == stage and x['candidate'] == 'baseline' and x['seed'] == r['seed'] and x['condition'] == r['condition']), None)
            if r['metrics']['completion_rate'] < spec.min_completion: failures.append('Below minimum completion')
            if r['metrics']['invalid'] / r['metrics']['requested'] > spec.max_invalid_fraction: failures.append('Too many invalid routes')
            if b and r['metrics']['completion_rate'] < b['metrics']['completion_rate'] - spec.max_completion_drop - 1e-10: failures.append('Completion loss exceeds paired constraint')
        if any(metrics[k]['mean'] is None for k in spec.objectives): failures.append('Objective unavailable; insufficient group or completed-trip data')
        rows.append({'id': c['id'], 'label': c['label'], 'changes': c['changes'], 'scenario': c['scenario'], 'metrics': {k: v['mean'] for k, v in metrics.items()}, 'estimates': metrics, 'feasible': not failures, 'constraint_failures': sorted(set(failures)), 'run_ids': [r['run_id'] for r in entries], 'n': len(entries)})
    frontier = nondominated(rows, spec.objectives)
    for r in rows: r['pareto'] = r['id'] in frontier
    return rows

def run_experiment(id):
    folder = DATA / 'tasks' / id
    spec = ExperimentSpec(**task(id)['spec'])
    planned = json.loads((folder / 'plan.json').read_text())
    if describe(spec.scenario.network)['version'] != planned['network_version']:
        raise ValueError('Network content changed since planning; create a new study.')
    checkpoint = folder / 'checkpoint.json'
    records = json.loads(checkpoint.read_text()) if checkpoint.exists() else []
    candidates = planned['candidates']
    current_stage = 'search'
    def cancelled(): return (folder / 'cancel').exists()
    def persist(): atomic_json(checkpoint, records)
    def trial(candidate, stage, cond, seed, matched):
        nonlocal current_stage
        current_stage = stage
        if cancelled(): raise InterruptedError('Study cancelled; completed trials are retained for resume')
        token = f'{stage}-{cond}-{seed}-{candidate["id"]}'
        existing = next((r for r in records if r['token'] == token), None)
        if existing: return existing
        run_id = f'{id}-{canonical_hash(token)[:16]}'
        run_folder = DATA / 'jobs' / run_id
        s = condition(candidate['scenario'], cond, spec, seed)
        run_folder.mkdir(parents=True, exist_ok=True)
        with connect() as c:
            c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?)', (run_id, 'running', 0, s.model_dump_json(), None, time.time()))
        update_task(id, 'running', len(records) / planned['maximum_runs'], {'stage': stage, 'completed_runs': len(records), 'maximum_runs': planned['maximum_runs'], 'candidate': candidate['label']})
        try:
            result = execute(s, run_folder, cancelled=cancelled, trip_manifest=matched, record=False)
            update_job(run_id, 'completed', 1)
        except InterruptedError:
            update_job(run_id, 'cancelled', error='Parent study cancelled')
            raise
        except Exception as e:
            update_job(run_id, 'failed', error=str(e))
            raise
        row = {'token': token, 'run_id': run_id, 'stage': stage, 'condition': cond, 'seed': seed, 'candidate': candidate['id'], 'metrics': result['metrics'], 'manifest_hash': result['manifest_hash'], 'network_version': result['network']['version'], 'groups': result['groups']}
        records.append(row)
        persist()
        return row
    def batch(items, stage, conditions, seeds):
        for cond in conditions:
            for seed in seeds:
                matched = manifest(condition(candidates[0]['scenario'], cond, spec, seed))
                for item in items: trial(item, stage, cond, seed, matched)
    try:
        batch(candidates, 'search', ['uniform'], spec.search_seeds)
        search = summarize_candidates(candidates, records, spec, 'search')
        alternatives = sorted([r for r in search if r['id'] != 'baseline'], key=lambda r: (not r['feasible'], r['metrics'].get(spec.objectives[0]) if r['metrics'].get(spec.objectives[0]) is not None else float('inf'), r['id']))
        shortlist_ids = [r['id'] for r in alternatives[:spec.finalists]]
        shortlist = [candidates[0]] + [c for c in candidates if c['id'] in shortlist_ids]
        batch(shortlist, 'tuning', ['peak'], spec.tuning_seeds)
        tuning = summarize_candidates(shortlist, records, spec, 'tuning')
        frozen_file = folder / 'frozen.json'
        if frozen_file.exists():
            frozen = json.loads(frozen_file.read_text())
        else:
            frozen = list(shortlist)
            if spec.ablations:
                for c in shortlist[1:]:
                    variants = []
                    if c['scenario'].get('transit_extension', 0): variants.append(('no-priority', {'transit_extension': 0}))
                    if c['scenario']['controller'] == 'pressure': variants.append(('no-downstream', {'pressure_downstream': False}))
                    for name, patch in variants:
                        scenario = {**c['scenario'], **patch, 'name': c['label'] + ' · ' + name}
                        frozen.append({'id': c['id'] + '-' + name, 'label': scenario['name'], 'scenario': scenario, 'changes': {**c['changes'], **patch}, 'ablation_of': c['id']})
            # This file is written before the first held-out execution; it is never overwritten on resume.
            atomic_json(frozen_file, frozen)
        batch(frozen, 'evaluation', spec.conditions, spec.evaluation_seeds)
        evaluation = summarize_candidates(frozen, records, spec, 'evaluation')
        paired = []
        for c in frozen[1:]:
            for cond in spec.conditions:
                rows = [r for r in records if r['stage'] == 'evaluation' and r['candidate'] == c['id'] and r['condition'] == cond]
                differences = []
                for r in rows:
                    b = next(x for x in records if x['stage'] == 'evaluation' and x['candidate'] == 'baseline' and x['condition'] == cond and x['seed'] == r['seed'])
                    ar = json.loads((DATA / 'jobs' / b['run_id'] / 'result.json').read_text())
                    br = json.loads((DATA / 'jobs' / r['run_id'] / 'result.json').read_text())
                    check = compare(ar, br)
                    if not check['compatible']: raise ValueError('Unmatched experimental pair: ' + ', '.join(check['reasons']))
                    differences.append({'seed': r['seed'], 'baseline': b['run_id'], 'candidate': r['run_id'], 'differences': {x['metric']: x['difference'] for x in check['rows']}})
                effects = {key: estimate([d['differences'].get(key) for d in differences]) for key in METRICS}
                for value in effects.values(): value['standardized_paired_effect'] = value['mean'] / value['sd'] if value['sd'] else None
                paired.append({'candidate': c['id'], 'condition': cond, 'pairs': differences, 'effects': effects})
        report = {'schema_version': 2, 'id': id, 'question': 'Improve movement without hiding journeys, people or streets that become worse off.', 'spec': spec.model_dump(), 'plan': planned, 'frozen': frozen, 'search': search, 'tuning': tuning, 'evaluation': evaluation, 'paired': paired, 'records': records, 'completed_runs': len(records), 'status': 'completed', 'interpretation': 'Best among evaluated candidates only. A frontier is not a global optimum. Inconclusive and adverse effects are valid findings.', 'interval_caveat': 'Runs are replicates; conditions are reported separately for inference. Pooled candidate summaries describe tested coverage, not independent generalisation samples.'}
        atomic_json(folder / 'result.json', report)
        update_task(id, 'completed', 1, {'stage': 'completed', 'completed_runs': len(records)})
    except InterruptedError as e:
        update_task(id, 'cancelled', len(records) / planned['maximum_runs'], {'stage': current_stage, 'completed_runs': len(records)}, str(e))
    except Exception as e:
        update_task(id, 'failed', len(records) / planned['maximum_runs'], {'stage': current_stage, 'completed_runs': len(records)}, str(e))
