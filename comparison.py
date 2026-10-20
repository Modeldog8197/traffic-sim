"""The single comparison contract used by the UI, research and exports."""
import hashlib
import json

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def compare(a, b):
    reasons = []
    checks = {
        'network content': (a['network']['version'], b['network']['version']),
        'trip manifest': (a['manifest_hash'], b['manifest_hash']),
        'evaluation horizon': (a['metrics']['horizon'], b['metrics']['horizon']),
        'warm-up': (a['scenario']['warmup'], b['scenario']['warmup']),
        'measurement version': (a.get('measurement_version', 1), b.get('measurement_version', 1)),
        'engine': (a['engine'], b['engine']),
        'routing policy': (a['scenario'].get('routing', 'departure_fastest'), b['scenario'].get('routing', 'departure_fastest')),
        'occupancy assumptions': ((a['scenario'].get('car_occupancy', 1.5), a['scenario'].get('bus_occupancy', 30)), (b['scenario'].get('car_occupancy', 1.5), b['scenario'].get('bus_occupancy', 30))),
    }
    for label, (left, right) in checks.items():
        if left != right:
            reasons.append(f'Mismatched {label}')
    keys = ['mean', 'delay', 'p95', 'completion_rate', 'completed', 'invalid', 'unfinished', 'bus_mean', 'person_loss', 'full_demand_loss', 'co2_kg', 'queue_seconds', 'od_inequality']
    rows = []
    for key in keys:
        av, bv = a['metrics'].get(key), b['metrics'].get(key)
        rows.append({'metric': key, 'baseline': av, 'candidate': bv, 'difference': bv - av if not reasons and av is not None and bv is not None else None})
    outcome = 'inconclusive'
    if not reasons:
        completion = b['metrics']['completion_rate'] - a['metrics']['completion_rate']
        delay = (b['metrics'].get('mean') or 0) - (a['metrics'].get('mean') or 0)
        outcome = 'trade-off' if completion < 0 and delay < 0 else 'worse under these conditions' if completion < 0 and delay >= 0 else 'single paired run; uncertainty not estimated'
    return {'schema_version': 2, 'compatible': not reasons, 'reasons': reasons, 'rows': rows, 'interpretation': outcome, 'network_version': a['network']['version'], 'manifest_hash': a['manifest_hash'], 'sample_sizes': [a['metrics']['sample_size'], b['metrics']['sample_size']]}
