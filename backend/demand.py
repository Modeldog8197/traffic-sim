"""Demand v2: independent, named RNG streams; interventions never regenerate it."""
import hashlib
import json
import random
import sumolib
from .network import net_path

def stream(seed, name):
    return random.Random(int(hashlib.sha256(f'citylab-demand-v2:{seed}:{name}'.encode()).hexdigest()[:16], 16))

def manifest(s, net=None):
    net = net or sumolib.net.readNet(str(net_path(s.network)))
    edges = sorted(net.getEdges(), key=lambda e: e.getID())
    ids = {e.getID() for e in edges}
    for pair in s.od:
        if pair.origin not in ids or pair.destination not in ids or pair.origin == pair.destination:
            raise ValueError('OD pairs require two different road IDs from this network.')
    origins, departures, classes = (stream(s.seed, name) for name in ['origins', 'departures', 'classes'])
    trips = []
    for line in s.transit:
        if any(e not in ids for e in line.route): raise ValueError(f'Bus {line.id}: unknown route edge.')
        for a, b in zip(line.route, line.route[1:]):
            if net.getEdge(b) not in net.getEdge(a).getOutgoing(): raise ValueError(f'Bus {line.id}: {a} does not connect to {b}.')
        positions = []
        for stop in line.stops:
            if stop.edge not in line.route: raise ValueError(f'Bus {line.id}: stop must be on its route.')
            edge = net.getEdge(stop.edge)
            if stop.lane >= edge.getLaneNumber() or stop.position > edge.getLength() - 1:
                raise ValueError(f'Bus stop on {stop.edge}: lane or position exceeds the road geometry.')
            if not edge.getLane(stop.lane).allows('bus'): raise ValueError('Bus stop lane does not permit buses.')
            positions.append((line.route.index(stop.edge), stop.position))
        if positions != sorted(positions) or len(set(positions)) != len(positions):
            raise ValueError('Bus stops must be distinct and ordered along the route.')
        times = sorted(line.departures or list(range(line.first_departure, s.duration, line.headway)))
        if len(times) != len(set(times)) or any(t >= s.duration for t in times):
            raise ValueError('Bus departure times must be unique and precede the demand duration.')
        reference = sum(net.getEdge(e).getLength() / min(net.getEdge(e).getSpeed(), 22) for e in line.route)
        for i, depart in enumerate(times):
            trips.append({'id': f'bus_{line.id}_{i:04d}', 'from': line.route[0], 'to': line.route[-1], 'depart': depart, 'kind': 'bus', 'reference': reference, 'service': line.id, 'service_route': line.route, 'stops': [stop.model_dump() for stop in line.stops]})
    if len(trips) > s.demand: raise ValueError('Bus schedules exceed requested trips. Increase total demand or headway.')
    for i in range(s.demand - len(trips)):
        kind = 'passenger' if s.transit else ('bus' if classes.random() < s.bus_fraction else 'passenger')
        candidates = [e for e in edges if any(l.allows(kind) for l in e.getLanes())]
        if len(candidates) < 2: raise ValueError(f'Network needs at least two {kind}-permitted roads.')
        if s.od:
            pair = origins.choices(s.od, weights=[p.weight for p in s.od], k=1)[0]
            a, b = net.getEdge(pair.origin), net.getEdge(pair.destination)
        else:
            a, b = origins.sample(candidates, 2)
        depart = (departures.betavariate(3, 3) if s.pattern == 'peak' else departures.random()) * s.duration
        path, cost = net.getFastestPath(a, b, vClass=kind)
        trips.append({'id': f'v{i:05d}', 'from': a.getID(), 'to': b.getID(), 'depart': min(s.duration - .5, round(depart, 1)), 'kind': kind, 'reference': cost if path else None, 'service': None, 'stops': []})
    for t in trips:
        t.update(occupancy=s.bus_occupancy if t['kind'] == 'bus' else s.car_occupancy, sigma=.5, length=12 if t['kind'] == 'bus' else 4.5, emission_class='HBEFA3/Bus' if t['kind'] == 'bus' else 'HBEFA3/PC_G_EU4')
    return sorted(trips, key=lambda t: (t['depart'], t['id']))

def digest(trips):
    return hashlib.sha256(json.dumps(trips, sort_keys=True).encode()).hexdigest()
