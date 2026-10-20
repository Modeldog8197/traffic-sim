"""Full-demand, person-weighted and distributional measures. No inferred field data."""
from collections import defaultdict
from statistics import mean
from .metrics import summarize

def outcomes(s, trips, completed, counts, waiting, emissions, stop_wait, edge_counts, warnings):
    horizon = s.duration + s.clearance
    m = summarize(trips, completed, counts['active'], counts['backlog'], counts['invalid'], horizon, s.warmup, warnings)
    m['otherwise_unserved'] = counts.get('otherwise_unserved', 0)
    m['unfinished'] += m['otherwise_unserved']
    arrived = {t['id']: t for t in completed}
    cohort = [t for t in trips if t['depart'] >= s.warmup]
    losses = {t['id']: arrived[t['id']]['travel_time'] if t['id'] in arrived else horizon - t['depart'] + horizon for t in cohort}
    m['full_demand_loss'] = mean(losses.values()) if losses else None
    total_people = sum(t['occupancy'] for t in cohort)
    m['person_loss'] = sum(losses[t['id']] * t['occupancy'] for t in cohort) / total_people if total_people else None
    m['person_completed_mean'] = sum(t['travel_time'] * t['occupancy'] for t in completed if t['depart'] >= s.warmup) / sum(t['occupancy'] for t in completed if t['depart'] >= s.warmup) if any(t['depart'] >= s.warmup for t in completed) else None
    m['co2_kg'] = emissions['co2_mg'] / 1_000_000
    m['nox_g'] = emissions['nox_mg'] / 1000
    m['queue_seconds'] = sum(waiting.values())
    m['bus_stop_seconds'] = sum(stop_wait.values())
    m['censored'] = len(cohort) - sum(t['id'] in arrived for t in cohort)
    groups = defaultdict(list)
    for t in trips:
        groups[f"OD · {t['from']} → {t['to']}"].append(t)
        groups[f"Class · {t['kind']}"].append(t)
    details = []
    for label, rows in groups.items():
        done = [arrived[t['id']] for t in rows if t['id'] in arrived]
        details.append({'group': label, 'requested': len(rows), 'completed': len(done), 'completion_rate': len(done) / len(rows), 'mean': mean(t['travel_time'] for t in done) if done else None, 'full_demand_loss': mean(arrived[t['id']]['travel_time'] if t['id'] in arrived else horizon - t['depart'] + horizon for t in rows), 'small_sample': len(rows) < 10})
    robust_groups = [g['full_demand_loss'] for g in details if g['group'].startswith('OD') and not g['small_sample']]
    m['od_inequality'] = max(robust_groups) - min(robust_groups) if len(robust_groups) >= 2 else None
    services = []
    for line in s.transit:
        scheduled = [t for t in trips if t.get('service') == line.id]
        done = sorted([arrived[t['id']] for t in scheduled if t['id'] in arrived], key=lambda t: t['arrival'])
        headways = [b['arrival'] - a['arrival'] for a, b in zip(done, done[1:])]
        services.append({'line': line.id, 'scheduled': len(scheduled), 'completed': len(done), 'mean_travel_time': mean(t['travel_time'] for t in done) if done else None, 'mean_terminal_headway': mean(headways) if headways else None, 'terminal_headways': headways, 'stop_seconds': sum(stop_wait.get(t['id'], 0) for t in scheduled), 'note': 'Terminal arrival headways for completed services; no passenger waiting inference.'})
    corridors = [{'name': name, 'edges': edges, 'entered_vehicles': sum(edge_counts.get(e, 0) for e in edges), 'note': 'Edge entries; a vehicle can be counted on multiple corridor edges.'} for name, edges in s.corridors.items()]
    return m, details, services, corridors


def corridor_outcomes(s, trips, completed, routes, edge_counts):
    """Current assigned-route cohorts; membership may change after rerouting."""
    arrived={t['id']:t for t in completed};h=s.duration+s.clearance;answer=[]
    for name,edges in s.corridors.items():
        selected=set(edges);cohort=[t for t in trips if selected.intersection(routes.get(t['id']) or [])]
        done=[arrived[t['id']] for t in cohort if t['id'] in arrived]
        loss=[arrived[t['id']]['travel_time'] if t['id'] in arrived else h-t['depart']+h for t in cohort]
        answer.append({'name':name,'edges':edges,'entered_vehicles':sum(edge_counts.get(e,0) for e in edges),'requested':len(cohort),'completed':len(done),'mean':mean(t['travel_time'] for t in done) if done else None,'full_demand_loss':mean(loss) if loss else None,'small_sample':len(cohort)<10,'note':'Cohort: trips assigned to at least one corridor edge. Rerouting can change membership; this is not a fixed paired population. Edge entries may count a trip more than once.'})
    return answer
