"""Run-level inference: deterministic bootstrap, never vehicle-level replication."""
import random
import statistics
from .metrics import percentile

def estimate(values):
    values = [v for v in values if v is not None]
    n = len(values)
    if not n:
        return {'n': 0, 'mean': None, 'sd': None, 'ci95': None}
    rng = random.Random(2147)
    draws = [statistics.mean(rng.choices(values, k=n)) for _ in range(2000)] if n >= 2 else []
    sd = statistics.stdev(values) if n >= 2 else None
    return {'n': n, 'mean': statistics.mean(values), 'sd': sd, 'ci95': [percentile(draws, .025), percentile(draws, .975)] if draws else None, 'method': '2000 seeded run-level bootstrap means; percentile 95% interval', 'caveat': 'Small-sample exploratory interval; no multiplicity correction' if n < 10 else 'Exploratory intervals; no multiplicity correction'}

def nondominated(rows, objectives):
    valid = [r for r in rows if r['feasible'] and all(r['metrics'].get(k) is not None for k in objectives)]
    return [r['id'] for r in valid if not any(all(q['metrics'][k] <= r['metrics'][k] for k in objectives) and any(q['metrics'][k] < r['metrics'][k] for k in objectives) for q in valid if q['id'] != r['id'])]
