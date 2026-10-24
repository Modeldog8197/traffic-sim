"""Bounded OSM conversion and lossless observation ingestion."""
import csv
import datetime
import hashlib
import io
import json
import math
import subprocess
import time
import xml.etree.ElementTree as ET
from .network import DATA, binary, describe
from .store import connect, task, update_task
from .frames import atomic_json

BOUNDS = (77.61, 12.88, 77.68, 12.94)

def convert_osm(raw, source='User-uploaded OSM XML', retrieval_date=None, progress=lambda p: None, cancelled=lambda: False):
    if len(raw) > 50_000_000: raise ValueError('OSM XML exceeds the 50 MB limit.')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('XML entities and DTDs are not allowed.')
    root = ET.fromstring(raw)
    nodes = root.findall('node')
    if root.tag != 'osm' or not nodes: raise ValueError('Expected OSM XML nodes, not PBF or an HTML error page.')
    for node in nodes:
        lon, lat = float(node.attrib['lon']), float(node.attrib['lat'])
        if not (BOUNDS[0] <= lon <= BOUNDS[2] and BOUNDS[1] <= lat <= BOUNDS[3]): raise ValueError('Nodes must fit HSR bounds: 77.61–77.68 longitude, 12.88–12.94 latitude.')
    id = 'hsr-' + hashlib.sha256(raw).hexdigest()[:12]
    folder = DATA / 'networks' / id
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'metadata.json').exists() and (folder / 'network.net.xml').exists(): return id
    (folder / 'source.osm.xml').write_bytes(raw)
    args = [binary('netconvert'), '--osm-files', str(folder / 'source.osm.xml'), '--output-file', str(folder / 'pending.net.xml'), '--lefthand', 'true', '--tls.guess', 'true', '--tls.default-type', 'static', '--tls.yellow.time', '3', '--tls.allred.time', '1', '--remove-edges.isolated', 'true']
    progress(.25)
    with (folder / 'conversion.log').open('w') as log:
        p = subprocess.Popen(args, stdout=log, stderr=log)
        start = time.monotonic()
        while p.poll() is None:
            if cancelled() or time.monotonic() - start > 120:
                p.terminate(); p.wait(timeout=5)
                raise InterruptedError('Conversion cancelled or exceeded 120 seconds')
            time.sleep(.1)
        if p.returncode: raise ValueError('netconvert failed: ' + (folder / 'conversion.log').read_text()[-1800:])
    progress(.8)
    (folder / 'pending.net.xml').replace(folder / 'network.net.xml')
    metadata = {'source': source, 'retrieved': retrieval_date or datetime.datetime.now(datetime.timezone.utc).isoformat(), 'license': 'ODbL 1.0', 'attribution': '© OpenStreetMap contributors', 'license_url': 'https://www.openstreetmap.org/copyright', 'source_sha256': hashlib.sha256(raw).hexdigest(), 'conversion_settings': args[1:], 'bounds': BOUNDS, 'assumptions': ['SUMO OSM type defaults fill missing speed/lane values.', 'Signals may be inferred with tls.guess; verify against field data.', 'No observed demand is supplied with geographic geometry.']}
    atomic_json(folder / 'metadata.json', metadata)
    info = describe(id)
    if not info['roads']: raise ValueError('Extract contains no usable roads.')
    progress(1)
    return id

def import_worker(id):
    folder = DATA / 'tasks' / id
    spec = task(id)['spec']
    try:
        network = convert_osm((folder / 'upload.osm').read_bytes(), spec.get('source', 'User upload'), progress=lambda p: update_task(id, 'running', p, {'stage': 'Converting and verifying topology'}), cancelled=lambda: (folder / 'cancel').exists())
        atomic_json(folder / 'result.json', describe(network))
        update_task(id, 'completed', 1, {'network': network})
    except InterruptedError as e: update_task(id, 'cancelled', error=str(e))
    except Exception as e: update_task(id, 'failed', error=str(e))

def parse_observations(raw, network, provenance='User-supplied observations'):
    if len(raw) > 5_000_000: raise ValueError('CSV exceeds 5 MB.')
    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    required = {'road_id', 'start_s', 'end_s', 'vehicle_count'}
    optional = {'mean_speed_mps', 'vehicle_class'}
    if not required.issubset(reader.fieldnames or []) or set(reader.fieldnames or []) - required - optional:
        raise ValueError('Columns: road_id,start_s,end_s,vehicle_count; optional mean_speed_mps,vehicle_class. Seconds and m/s only.')
    info = describe(network)
    known = {r['id'] for r in info['roads']}
    rows = []
    for number, row in enumerate(reader, 2):
        try:
            road = row['road_id'].strip()
            a, b = float(row['start_s']), float(row['end_s'])
            count = float(row['vehicle_count'])
            speed = float(row['mean_speed_mps']) if row.get('mean_speed_mps', '').strip() else None
            kind = row.get('vehicle_class', '').strip() or 'all'
            if road not in known: raise ValueError('unknown road ID')
            if not all(math.isfinite(v) for v in [a, b, count] + ([] if speed is None else [speed])): raise ValueError('non-finite number')
            if a < 0 or b <= a or b > 5400: raise ValueError('interval must satisfy 0 ≤ start < end ≤ 5400 seconds')
            if count < 0 or count != int(count) or count > 100000: raise ValueError('count must be an integer between 0 and 100000')
            if speed is not None and (speed < 0 or speed > 70 or count == 0): raise ValueError('speed must be 0–70 m/s and requires a positive count')
            if kind not in ('all', 'passenger', 'bus'): raise ValueError('class must be all, passenger or bus')
            if any(r['road_id'] == road and (r['vehicle_class'] == kind or 'all' in (kind, r['vehicle_class'])) and max(a, r['start_s']) < min(b, r['end_s']) for r in rows): raise ValueError('overlapping measurement intervals/classes')
            rows.append({'road_id': road, 'start_s': a, 'end_s': b, 'vehicle_count': int(count), 'mean_speed_mps': speed, 'vehicle_class': kind})
        except (ValueError, TypeError, KeyError) as e:
            raise ValueError(f'CSV row {number}: {e}') from e
    if not rows or len(rows) > 2000: raise ValueError('Provide 1–2000 measurement rows.')
    return {'schema_version': 2, 'network': network, 'network_version': info['version'], 'provenance': provenance, 'measurement': 'Directed-road entries in [start_s,end_s); optional arithmetic mean entry speed', 'source_hash': hashlib.sha256(raw).hexdigest(), 'rows': rows}
