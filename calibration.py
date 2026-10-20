"""Bounded demand fitting; disjoint time intervals and held-out stochastic seeds."""
import json
import itertools
from statistics import mean
from pydantic import BaseModel, Field, model_validator
from .models import Scenario
from .network import DATA
from .store import task, update_task, connect
from .frames import atomic_json
from .engine import execute

class CalibrationSpec(BaseModel):
    observation_id: str
    scenario: Scenario
    demand_values: list[int] = Field(default_factory=lambda: [80, 100, 120], min_length=1, max_length=6)
    bus_fractions: list[float] = Field(default_factory=lambda: [.1], min_length=1, max_length=4)
    fit_end: float = Field(60, gt=0)
    validation_start: float = Field(60, gt=0)
    fit_seeds: list[int] = [11, 12]
    validation_seeds: list[int] = [101, 102]
    budget: int = Field(16, ge=1, le=100)
    @model_validator(mode='after')
    def bounds(self):
        if self.fit_end > self.validation_start: raise ValueError('Fitting and validation intervals overlap.')
        if not self.fit_seeds or not self.validation_seeds or set(self.fit_seeds) & set(self.validation_seeds): raise ValueError('Provide disjoint fitting and validation seeds.')
        if any(not 0 <= s <= 2147483647 for s in self.fit_seeds + self.validation_seeds): raise ValueError('Invalid seed.')
        if any(not 1 <= n <= 2000 for n in self.demand_values) or any(not 0 <= f <= .5 for f in self.bus_fractions): raise ValueError('Demand or bus-share grid is out of bounds.')
        if self.scenario.transit and len(set(self.bus_fractions)) > 1: raise ValueError('With explicit bus schedules, calibrate demand only; bus share comes from the schedule.')
        if len(self.demand_values) * len(self.bus_fractions) * len(self.fit_seeds) + len(self.validation_seeds) > self.budget: raise ValueError('Calibration exceeds the chosen run budget.')
        return self

def residuals(rows, result):
    residuals = []
    for row in rows:
        crossings = [e for e in result['edge_crossings'] if e['road_id'] == row['road_id'] and row['start_s'] <= e['time'] < row['end_s'] and (row['vehicle_class'] == 'all' or row['vehicle_class'] == e['vehicle_class'])]
        predicted = len(crossings)
        speed = mean(e['speed_mps'] for e in crossings) if crossings else None
        residuals.append({**row, 'simulated_count': predicted, 'residual': predicted - row['vehicle_count'], 'simulated_speed_mps': speed, 'speed_residual': speed - row['mean_speed_mps'] if speed is not None and row['mean_speed_mps'] is not None else None})
    return {'rows': residuals, 'count_mae': mean(abs(r['residual']) for r in residuals), 'count_rmse': mean(r['residual'] ** 2 for r in residuals) ** .5, 'count_coverage': 1, 'speed_coverage': sum(r['speed_residual'] is not None for r in residuals) / max(1, sum(r['mean_speed_mps'] is not None for r in residuals))}

def run_calibration(id):
    folder = DATA / 'tasks' / id
    spec = CalibrationSpec(**task(id)['spec'])
    with connect() as c: row = c.execute('SELECT payload FROM observations WHERE id=?', (spec.observation_id,)).fetchone()
    try:
        if not row: raise ValueError('Observation dataset not found.')
        observations = json.loads(row[0])
        if observations['network'] != spec.scenario.network: raise ValueError('Observation and scenario networks differ.')
        fit = [r for r in observations['rows'] if r['end_s'] <= spec.fit_end]
        validation = [r for r in observations['rows'] if r['start_s'] >= spec.validation_start]
        if not fit or not validation: raise ValueError('Both fitting and validation intervals need observations.')
        if max(r['end_s'] for r in fit + validation) > spec.scenario.duration + spec.scenario.clearance: raise ValueError('Observation intervals exceed the simulation horizon.')
        candidates = []
        total = len(spec.demand_values) * len(spec.bus_fractions) * len(spec.fit_seeds) + len(spec.validation_seeds)
        done = 0
        def run(demand, fraction, seed, name):
            nonlocal done
            target = folder / name
            s = spec.scenario.model_copy(update={'demand': demand, 'bus_fraction': fraction, 'seed': seed, 'network_version': observations['network_version']})
            if (target / 'result.json').exists(): result = json.loads((target / 'result.json').read_text())
            else: result = execute(s, target, cancelled=lambda: (folder / 'cancel').exists(), record=False)
            done += 1
            update_task(id, 'running', done / total, {'stage': name, 'completed_runs': done})
            return result
        for demand, fraction in itertools.product(spec.demand_values, spec.bus_fractions):
            checks = [residuals(fit, run(demand, fraction, seed, f'fit-{demand}-{fraction}-{seed}')) for seed in spec.fit_seeds]
            candidates.append({'demand': demand, 'bus_fraction': fraction, 'fit_mae': mean(r['count_mae'] for r in checks), 'fit_runs': checks})
        selected = min(candidates, key=lambda r: (r['fit_mae'], r['demand'], r['bus_fraction']))
        atomic_json(folder / 'frozen.json', {k: selected[k] for k in ('demand', 'bus_fraction')})
        checks = [residuals(validation, run(selected['demand'], selected['bus_fraction'], seed, f'validation-{seed}')) for seed in spec.validation_seeds]
        report = {'schema_version': 2, 'spec': spec.model_dump(), 'observations': observations, 'candidates': candidates, 'selected': selected, 'validation': checks, 'validation_mae': mean(r['count_mae'] for r in checks), 'validation_rmse': mean(r['count_rmse'] for r in checks), 'completed_runs': done, 'interpretation': 'Synthetic fixture demonstration, not field validation' if 'synthetic' in observations['provenance'].lower() else 'Bounded model fit to supplied road-entry observations; not validation of the whole traffic system'}
        atomic_json(folder / 'result.json', report)
        update_task(id, 'completed', 1, {'completed_runs': done})
    except InterruptedError as e: update_task(id, 'cancelled', error=str(e))
    except Exception as e: update_task(id, 'failed', error=str(e))
