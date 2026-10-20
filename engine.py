"""An isolated SUMO adapter with immutable inputs and optional detailed recordings."""
import json
import shutil
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
import sumolib
import traci
import traci.constants as tc
from .models import Scenario
from .network import DATA, net_path, binary, describe
from .demand import manifest, digest
from .routing import validate_network
from .controllers import Controller
from .analysis import outcomes, corridor_outcomes
from .comparison import canonical_hash
from .frames import FrameWriter, atomic_json
from .store import update_job

APP_REVISION = 'citylab-2.0.0'

def execute(s, folder, progress=lambda x: None, cancelled=lambda: False, trip_manifest=None, record=True):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if not (folder / 'network.net.xml').exists():
        info = describe(s.network)
        if s.network_version and s.network_version != info['version']:
            raise ValueError('Network version changed. Reload the network before submitting.')
        shutil.copyfile(net_path(s.network), folder / 'network.net.xml')
        atomic_json(folder / 'network.json', info)
    info = json.loads((folder / 'network.json').read_text())
    net = sumolib.net.readNet(str(folder / 'network.net.xml'))
    trips = trip_manifest if trip_manifest is not None else manifest(s, net)
    routes, invalid = validate_network(s, trips, net, network_info=info, allow_all_invalid=True)
    invalid_set = set(invalid)
    root = ET.Element('routes')
    ET.SubElement(root, 'vType', id='car', vClass='passenger', length='4.5', maxSpeed='30', sigma='0.5', emissionClass='HBEFA3/PC_G_EU4')
    ET.SubElement(root, 'vType', id='bus', vClass='bus', length='12', maxSpeed='22', sigma='0.5', personCapacity='60', emissionClass='HBEFA3/Bus')
    for t in trips:
        path = routes[t['id']]
        if not path:
            continue
        vehicle = ET.SubElement(root, 'vehicle', id=t['id'], type='bus' if t['kind'] == 'bus' else 'car', depart=str(t['depart']), departLane='best', departSpeed='0')
        ET.SubElement(vehicle, 'route', edges=' '.join(path))
        for stop in t.get('stops', []):
            ET.SubElement(vehicle, 'stop', lane=f"{stop['edge']}_{stop['lane']}", endPos=str(stop['position']), duration=str(stop['dwell']))
    ET.ElementTree(root).write(folder / 'routes.xml')
    atomic_json(folder / 'manifest.json', trips)
    lookup = {t['id']: t for t in trips}
    completed, warnings, events, aggregate = [], [], [], []
    conn = None
    stdout = (folder / 'stdout.log').open('w')
    decision_file = (folder / 'decisions.ndjson').open('w') if record else None
    frame_writer = FrameWriter(folder) if record else None
    label = 'run-' + uuid.uuid4().hex
    try:
        traci.start([binary('sumo'), '-n', str(folder / 'network.net.xml'), '-r', str(folder / 'routes.xml'), '--seed', str(s.seed), '--step-length', '0.5', '--time-to-teleport', '-1', '--collision.action', 'warn', '--no-step-log', 'true', '--duration-log.disable', 'true', '--error-log', str(folder / 'sumo.log')], label=label, stdout=stdout)
        conn = traci.getConnection(label)
        version = conn.getVersion()[1]
        for eid, edit in s.roads.items():
            conn.edge.setMaxSpeed(eid, edit.speed)
            for lane in net.getEdge(eid).getLanes():
                if edit.closed or not edit.allowed:
                    conn.lane.setDisallowed(lane.getID(), ['all'])
                else:
                    conn.lane.setAllowed(lane.getID(), edit.allowed)
        controller = Controller(conn, s)
        horizon = s.duration + s.clearance
        def geo(p):
            return [77.638 + p[0] / 108500, 12.905 + p[1] / 111320] if info['synthetic'] else list(net.convertXY2LonLat(*p))
        waiting = {jid: 0.0 for jid in controller.plans}
        incoming = {jid: {a for a, b in controller.movements[jid]} for jid in waiting}
        edge_ids = [e.getID() for e in net.getEdges()]
        edge_counts, stop_wait, previous_edge = {}, {}, {}
        crossings = []
        emissions = {'co2_mg': 0.0, 'nox_mg': 0.0}
        departed = set()
        peak = 0
        vars = [tc.VAR_SPEED, tc.VAR_ROAD_ID, tc.VAR_LANE_ID, tc.VAR_LANEPOSITION, tc.VAR_ROUTE_INDEX, tc.VAR_CO2EMISSION, tc.VAR_NOXEMISSION, tc.VAR_STOPSTATE]
        if record:
            vars.extend([tc.VAR_POSITION, tc.VAR_ANGLE])
        for eid, edit in s.roads.items():
            if edit.closed:
                events.append({'time': 0, 'kind': 'disruption', 'road': eid, 'text': f'{eid} closed for this entire run'})
        for step in range(1, horizon * 2 + 1):
            if step % 10 == 0:
                if cancelled(): raise InterruptedError('Cancelled by user')
                if time.perf_counter() - started > 600: raise TimeoutError('Simulation exceeded the 600-second wall-time limit')
            conn.simulationStep()
            now = step * .5
            for vid in conn.simulation.getDepartedIDList():
                departed.add(vid)
                conn.vehicle.subscribe(vid, vars)
            for vid in conn.simulation.getArrivedIDList():
                t = lookup[vid]
                travel = now - t['depart']
                completed.append({**t, 'arrival': now, 'travel_time': travel, 'delay': travel - (t['reference'] or 0)})
            warnings.extend(f'Teleport at {now}s: {v}' for v in conn.simulation.getStartingTeleportIDList())
            subscriptions = conn.vehicle.getAllSubscriptionResults()
            active_ids = set(conn.vehicle.getIDList())
            vehicles = {}
            lanes = {}
            edge_values = {e: {'queue': 0, 'count': 0, 'speeds': []} for e in edge_ids}
            for vid in sorted(active_ids):
                row = subscriptions.get(vid)
                if not row:
                    raise RuntimeError(f'Missing subscribed state for active vehicle {vid}')
                v = {'id': vid, 'lane': row[tc.VAR_LANE_ID], 'road': row[tc.VAR_ROAD_ID], 'lane_position': row[tc.VAR_LANEPOSITION], 'route_index': row[tc.VAR_ROUTE_INDEX], 'speed': row[tc.VAR_SPEED], 'kind': lookup[vid]['kind']}
                if record:
                    v.update(position=geo(row[tc.VAR_POSITION]), angle=row[tc.VAR_ANGLE])
                vehicles[vid] = v
                lanes[v['lane']] = lanes.get(v['lane'], 0) + (v['speed'] < .1)
                emissions['co2_mg'] += max(0, row[tc.VAR_CO2EMISSION]) * .5
                emissions['nox_mg'] += max(0, row[tc.VAR_NOXEMISSION]) * .5
                if row[tc.VAR_STOPSTATE] & 1 and v['kind'] == 'bus':
                    stop_wait[vid] = stop_wait.get(vid, 0) + .5
                if v['road'] in edge_values:
                    e = edge_values[v['road']]
                    e['count'] += 1
                    e['queue'] += v['speed'] < .1
                    e['speeds'].append(v['speed'])
                    if previous_edge.get(vid) != v['road']:
                        edge_counts[v['road']] = edge_counts.get(v['road'], 0) + 1
                        crossings.append({'road_id':v['road'],'time':now,'vehicle_class':v['kind'],'speed_mps':v['speed']})
                previous_edge[vid] = v['road']
            decisions = controller.step(now, vehicles, routes)
            if decision_file:
                decision_file.write(json.dumps({'time': now, 'junctions': decisions}, separators=(',', ':')) + '\n')
            queues = {jid: sum(lanes.get(lane, 0) for lane in ls) for jid, ls in incoming.items()}
            for jid, q in queues.items():
                waiting[jid] += q * .5
            due = sum(t['depart'] <= now for t in trips if t['id'] not in invalid_set)
            missing = len(departed) - len(completed) - len(active_ids)
            counts = {'requested': len(trips), 'scheduled': len(trips) - len(invalid) - due, 'active': len(active_ids), 'completed': len(completed), 'backlog': due - len(departed), 'invalid': len(invalid), 'otherwise_unserved': missing}
            if min(counts.values()) < 0 or counts['requested'] != sum(v for k, v in counts.items() if k != 'requested'):
                raise RuntimeError(f'Vehicle accounting failed at {now}s: {counts}')
            if step % 4 == 0 or step == horizon * 2:
                total_q = sum(queues.values())
                if total_q >= peak + 5:
                    peak = total_q
                    events.append({'time': now, 'kind': 'queue_peak', 'text': f'New queue high: {peak} vehicles across signal approaches'})
                if aggregate and aggregate[-1]['queue'] > 0 and total_q == 0:
                    events.append({'time': now, 'kind': 'recovery', 'text': 'All signal-approach queues returned to zero'})
                for jid, decision in decisions.items():
                    if decision['action'] == 'end' or 'priority' in decision['reason'].lower():
                        events.append({'time': now, 'kind': 'controller', 'junction': jid, 'text': decision['reason']})
                aggregate.append({'time': now, 'counts': counts, 'queue': total_q, 'co2_kg': emissions['co2_mg'] / 1e6})
                if frame_writer:
                    edges = {eid: {'queue': e['queue'], 'count': e['count'], 'speed': sum(e['speeds']) / len(e['speeds']) if e['speeds'] else None} for eid, e in edge_values.items()}
                    frame_writer.append({'time': now, 'vehicles': list(vehicles.values()), 'edges': edges, 'queues': queues, 'signals': {j: d['state'] for j, d in decisions.items()}, 'decisions': decisions, 'counts': counts})
                progress(now / horizon)
        conn.close()
        conn = None
        warnings.extend(line for line in (folder / 'sumo.log').read_text().splitlines() if line.strip())
        metrics, groups, services, corridors = outcomes(s, trips, completed, counts, waiting, emissions, stop_wait, edge_counts, warnings)
        corridors = corridor_outcomes(s, trips, completed, routes, edge_counts)
        result = {'schema_version': 2, 'measurement_version': 2, 'application_revision': APP_REVISION, 'scenario': s.model_dump(), 'configuration_hash': canonical_hash(s.model_dump()), 'manifest': trips, 'manifest_hash': digest(trips), 'random_streams': {'demand': 'SHA256(seed, origins/departures/classes), v2', 'dynamics': s.seed}, 'routes': routes, 'network': info, 'engine': version, 'metrics': metrics, 'groups': groups, 'transit_services': services, 'corridors': corridors, 'completed_trips': completed, 'junction_waiting_seconds': waiting, 'edge_entries': edge_counts, 'edge_crossings':crossings, 'aggregate': aggregate, 'events': events, 'invalid_trip_ids': invalid, 'recorded': record, 'wall_seconds': time.perf_counter() - started, 'assumptions': {'demand': 'Generated; not observed', 'car_occupancy': s.car_occupancy, 'bus_occupancy': s.bus_occupancy, 'routing': s.routing, 'bus_stops': 'Explicit service stops only; no arbitrary midpoint dwell', 'emissions': 'HBEFA3/PC_G_EU4 and HBEFA3/Bus; rate integration at 0.5 s', 'full_demand_loss': 'Completed travel time, else elapsed since requested departure + one horizon penalty; seconds/requested trip', 'timestep': .5, 'frame_interval': 2}}
        atomic_json(folder / 'result.json', result)
        return result
    finally:
        if conn:
            try: conn.close()
            except Exception: pass
        stdout.close()
        if decision_file: decision_file.close()

def worker(id, payload):
    folder = DATA / 'jobs' / id
    try:
        update_job(id, 'running')
        execute(Scenario(**payload), folder, lambda p: update_job(id, 'running', p), lambda: (folder / 'cancel').exists())
        update_job(id, 'completed', 1)
    except InterruptedError:
        update_job(id, 'cancelled', error='Cancelled by user')
    except Exception as e:
        update_job(id, 'failed', error=str(e))
        (folder / 'traceback.txt').write_text(traceback.format_exc())
