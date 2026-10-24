import os
import signal
import csv
import io
import json
import multiprocessing
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
import sumolib
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .network import DATA, ROOT, describe, binary, net_path, ensure_synthetic
from .models import Scenario, ExperimentSpec
from .store import connect, job, update_job, setting, task, update_task
from .engine import worker
from .demand import manifest
from .routing import validate_network
from .frames import page, atomic_json
from .comparison import compare
from .explorer import plan, run_experiment
from .imports import import_worker, parse_observations
from .calibration import CalibrationSpec, run_calibration
from .exports import report_html, report_pdf, evidence_bundle

processes = {}
process_lock = threading.RLock()

def dispatch(kind, id, payload):
    if hasattr(os, 'setsid'): os.setsid()
    parent=os.getppid()
    def watch_parent():
        while True:
            time.sleep(.5)
            if os.getppid()!=parent:
                if hasattr(os, 'killpg'): os.killpg(os.getpid(), signal.SIGTERM)
                else: os._exit(1)
    threading.Thread(target=watch_parent, daemon=True).start()
    if kind == 'job': worker(id, payload)
    elif kind == 'experiment': run_experiment(id)
    elif kind == 'import': import_worker(id)
    elif kind == 'calibration': run_calibration(id)
    elif kind == 'playback':
        from .playback_jobs import record_pair
        record_pair(id)

def launch(kind, id, payload=None):
    with process_lock:
        for key, (p, k) in list(processes.items()):
            if not p.is_alive(): p.join(); del processes[key]
        if len(processes) >= 2: raise HTTPException(429, 'Two workers are active. Cancel or wait before starting another task.')
        p = multiprocessing.get_context('spawn').Process(target=dispatch, args=(kind, id, payload))
        p.start()
        processes[id] = (p, kind)

def recover():
    with connect() as c:
        c.execute("UPDATE jobs SET status='interrupted',error='Server restarted; rerun from the preserved configuration' WHERE status IN ('queued','running','cancelling')")
        c.execute("UPDATE tasks SET status='interrupted',error='Server restarted; completed trials are retained. Resume to continue.' WHERE status IN ('queued','running','cancelling')")

@asynccontextmanager
async def lifespan(app):
    from .bootstrap import install_examples
    install_examples()
    ensure_synthetic()
    recover()
    yield
    for id, (p, kind) in list(processes.items()):
        if p.is_alive():
            folder = DATA / ('jobs' if kind == 'job' else 'tasks') / id
            (folder / 'cancel').touch()
            p.join(5)
            if p.is_alive():
                if hasattr(os, 'killpg'): os.killpg(p.pid, signal.SIGTERM)
                else: p.terminate()
                p.join(3)
            (update_job if kind == 'job' else update_task)(id, 'interrupted', error='Server shutdown; inputs retained')
app = FastAPI(title='CityLab', version='2.0.0', lifespan=lifespan)

def getjob(id):
    value = job(id)
    if not value: raise HTTPException(404, 'Run unavailable. Choose another recorded run.')
    proc = processes.get(id)
    if proc and not proc[0].is_alive() and value['status'] in ('running','queued','cancelling'):
        update_job(id, 'failed', error='Worker exited unexpectedly; configuration retained')
        value = job(id)
    return value

def gettask(id):
    value = task(id)
    if not value: raise HTTPException(404, 'Task not found')
    proc = processes.get(id)
    if proc and not proc[0].is_alive() and value['status'] in ('running','queued','cancelling'):
        update_task(id, 'interrupted', error='Worker exited. Resume pending trials.')
        value = task(id)
    return value

@app.get('/api/health')
def health():
    try: return {'engine': 'SUMO', 'available': bool(binary('sumo')), 'revision': 'citylab-2.0.0'}
    except Exception as e: return {'engine': 'SUMO', 'available': False, 'error': str(e)}

@app.get('/api/defaults')
def defaults(): return Scenario().model_dump()

@app.get('/api/networks')
def networks():
    ensure_synthetic()
    return [{'id': p.name, 'label': 'Synthetic demonstration network' if p.name == 'synthetic' else 'HSR Layout · '+p.name[-6:]} for p in (DATA/'networks').glob('*') if (p/'network.net.xml').exists()]

@app.get('/api/network/{id}')
def network(id):
    try: return describe(id)
    except Exception as e: raise HTTPException(400, str(e))

@app.post('/api/validate')
def validate(s: Scenario):
    try:
        info = describe(s.network)
        if s.network_version and s.network_version != info['version']: raise ValueError('Network changed. Reload it before running.')
        trips = manifest(s)
        routes, invalid = validate_network(s, trips, sumolib.net.readNet(str(net_path(s.network))))
        return {'valid': True, 'invalid_trips': len(invalid), 'warnings': [f'{len(invalid)} trips cannot be served. Inspect closed endpoints, service routes and access restrictions.'] if invalid else [], 'network_version': info['version']}
    except Exception as e: raise HTTPException(422, str(e))

@app.get('/api/scenarios')
def scenarios():
    with connect() as c:
        return [{'id': r[0], **Scenario(**json.loads(r[1])).model_dump()} for r in c.execute('SELECT id,payload FROM scenarios')]

@app.put('/api/scenarios/{id}')
def save(id: str, s: Scenario):
    with connect() as c: c.execute('INSERT OR REPLACE INTO scenarios VALUES (?,?)', (id, s.model_dump_json()))
    return {'id': id, **s.model_dump()}

@app.delete('/api/scenarios/{id}')
def delete(id: str):
    with connect() as c: c.execute('DELETE FROM scenarios WHERE id=?', (id,))
    return {'deleted': True}

@app.get('/api/baseline')
def baseline():
    id = setting('baseline')
    value = job(id) if id else None
    return {'id': id if value and value['status'] == 'completed' and (DATA/'jobs'/id/'result.json').exists() else None, 'unavailable': bool(id and (not value or not (DATA/'jobs'/id/'result.json').exists()))}

class Baseline(BaseModel):
    id: str

@app.put('/api/baseline')
def set_baseline(value: Baseline):
    result(value.id)
    setting('baseline', value.id)
    return {'id': value.id}

@app.post('/api/jobs', status_code=202)
def start(s: Scenario):
    validation = validate(s)
    s = s.model_copy(update={'network_version': validation['network_version']})
    id = uuid.uuid4().hex
    folder = DATA/'jobs'/id
    folder.mkdir(parents=True)
    shutil.copyfile(net_path(s.network), folder/'network.net.xml')
    atomic_json(folder/'network.json', describe(s.network))
    with connect() as c: c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?)', (id, 'queued', 0, s.model_dump_json(), None, time.time()))
    try: launch('job', id, s.model_dump())
    except HTTPException as e: update_job(id, 'failed', error=e.detail); raise
    return getjob(id)

@app.get('/api/jobs')
def jobs():
    with connect() as c: ids = [r[0] for r in c.execute("SELECT id FROM jobs WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE jobs.id LIKE tasks.id || '-%') ORDER BY created DESC LIMIT 250")]
    return [getjob(id) for id in ids]

@app.get('/api/jobs/{id}')
def status(id: str): return getjob(id)

@app.post('/api/jobs/{id}/cancel')
def cancel(id: str):
    j = getjob(id)
    if j['status'] in ('queued','running'):
        (DATA/'jobs'/id/'cancel').touch()
        update_job(id, 'cancelling', j['progress'])
    return getjob(id)

@app.get('/api/jobs/{id}/network')
def recorded_network(id: str):
    getjob(id)
    path = DATA/'jobs'/id/'network.json'
    if not path.exists(): raise HTTPException(404, 'Recorded network unavailable')
    return json.loads(path.read_text())

@app.get('/api/jobs/{id}/frames')
def frames(id: str, offset: int = 0, limit: int = 64):
    getjob(id)
    return page(DATA/'jobs'/id, offset, limit)

@app.get('/api/jobs/{id}/result')
def result(id: str):
    if getjob(id)['status'] != 'completed': raise HTTPException(409, 'Final results are available only after completion')
    path = DATA/'jobs'/id/'result.json'
    if not path.exists(): raise HTTPException(410, 'Result artifact is unavailable; rerun the preserved scenario')
    value = json.loads(path.read_text())
    value.setdefault('schema_version', 1)
    value.setdefault('measurement_version', 1)
    return value

@app.post('/api/jobs/{id}/record', status_code=202)
def record(id: str):
    r = result(id)
    if r.get('measurement_version') != 2: raise HTTPException(409, 'Legacy recordings use another measurement model. Edit a copy to create a new v2 experiment.')
    s = Scenario(**r['scenario'])
    s.network_version = r['network']['version']
    return start(s)

@app.get('/api/jobs/{id}/export.csv')
def export_csv(id: str):
    r = result(id)
    out = io.StringIO(); w = csv.writer(out); w.writerow(['metric','value','run_id'])
    for key, value in r['metrics'].items(): w.writerow([key, json.dumps(value), id])
    return Response(out.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="citylab-{id}.csv"'})

@app.get('/api/jobs/{id}/export.json')
def export_json(id: str): return result(id)

@app.get('/api/compare')
def comparison(baseline: str, candidate: str):
    return {'baseline_id': baseline, 'candidate_id': candidate, **compare(result(baseline), result(candidate))}

@app.get('/api/compare/export')
def comparison_export(baseline: str, candidate: str):
    value = comparison(baseline, candidate)
    if not value['compatible']: raise HTTPException(409, value['reasons'])
    return Response(json.dumps(value, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="citylab-comparison.json"'})

@app.post('/api/experiments/plan')
def experiment_plan(spec: ExperimentSpec):
    try: return plan(spec)
    except Exception as e: raise HTTPException(422, str(e))

def new_task(kind, payload):
    id = uuid.uuid4().hex
    (DATA/'tasks'/id).mkdir(parents=True)
    with connect() as c: c.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)', (id, kind, 'queued', 0, json.dumps(payload), '{}', None, time.time()))
    return id

@app.post('/api/experiments', status_code=202)
def experiment_start(spec: ExperimentSpec):
    planned = experiment_plan(spec)
    id = new_task('experiment', spec.model_dump())
    atomic_json(DATA/'tasks'/id/'plan.json', planned)
    try: launch('experiment', id)
    except HTTPException as e: update_task(id, 'failed', error=e.detail); raise
    return gettask(id)

class PairRecording(BaseModel):
    baseline: str
    candidate: str

@app.post('/api/playback-pairs', status_code=202)
def playback_pair(value: PairRecording):
    a,b=result(value.baseline),result(value.candidate)
    if a.get('measurement_version')!=2 or b.get('measurement_version')!=2: raise HTTPException(409,'Exact playback reruns require v2 results')
    check=compare(a,b)
    if not check['compatible']: raise HTTPException(409,check['reasons'])
    id=new_task('playback',value.model_dump())
    try: launch('playback',id)
    except HTTPException as e: update_task(id,'failed',error=e.detail);raise
    return gettask(id)

@app.get('/api/tasks')
def tasks():
    with connect() as c: ids = [r[0] for r in c.execute('SELECT id FROM tasks ORDER BY created DESC LIMIT 100')]
    return [gettask(id) for id in ids]

@app.get('/api/tasks/{id}')
def task_status(id: str): return gettask(id)

@app.post('/api/tasks/{id}/cancel')
def task_cancel(id: str):
    value = gettask(id)
    if value['status'] in ('running','queued'):
        (DATA/'tasks'/id/'cancel').touch()
        update_task(id, 'cancelling', value['progress'], value['detail'])
    return gettask(id)

@app.post('/api/tasks/{id}/resume')
def task_resume(id: str):
    value = gettask(id)
    if value['status'] not in ('cancelled','failed','interrupted'): raise HTTPException(409, 'Only stopped tasks can resume')
    (DATA/'tasks'/id/'cancel').unlink(missing_ok=True)
    update_task(id, 'queued', value['progress'], value['detail'])
    try: launch(value['kind'], id)
    except HTTPException as e:
        update_task(id, 'interrupted', value['progress'], value['detail'], e.detail)
        raise
    return gettask(id)

@app.get('/api/tasks/{id}/result')
def task_result(id: str):
    if gettask(id)['status'] != 'completed': raise HTTPException(409, 'Partial work is not a final result. Wait or resume the task.')
    return json.loads((DATA/'tasks'/id/'result.json').read_text())

@app.get('/api/tasks/{id}/report.html')
def report(id: str): return HTMLResponse(report_html(task_result(id)))

@app.get('/api/tasks/{id}/report.pdf')
def pdf_export(id: str):
    path=report_pdf(task_result(id), DATA/'tasks'/id/'report.pdf')
    return FileResponse(path, media_type='application/pdf', filename='citylab-report.pdf')

@app.get('/api/tasks/{id}/evidence.zip')
def evidence(id: str): return FileResponse(evidence_bundle(task_result(id), DATA/'tasks'/id), filename='citylab-evidence.zip')

async def bounded_body(request, maximum):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum: raise HTTPException(413, f'Upload exceeds {maximum // 1_000_000} MB')
    return bytes(body)

@app.post('/api/imports/osm', status_code=202)
async def osm_upload(request: Request):
    raw = await bounded_body(request, 50_000_000)
    id = new_task('import', {'source': 'User-uploaded OSM XML'})
    (DATA/'tasks'/id/'upload.osm').write_bytes(raw)
    try: launch('import', id)
    except HTTPException as e: update_task(id, 'failed', error=e.detail); raise
    return gettask(id)

@app.post('/api/observations/{network}')
async def observation_upload(network: str, request: Request):
    raw = await bounded_body(request, 5_000_000)
    provenance = request.headers.get('X-CityLab-Provenance', 'User-supplied observations')[:500]
    try: value = parse_observations(raw, network, provenance=provenance)
    except Exception as e: raise HTTPException(422, str(e))
    id = uuid.uuid4().hex
    folder = DATA/'observations'/id; folder.mkdir(parents=True)
    (folder/'original.csv').write_bytes(raw)
    with connect() as c: c.execute('INSERT INTO observations VALUES (?,?,?,?)', (id, network, json.dumps(value), time.time()))
    return {'id': id, **value}

@app.get('/api/observations')
def observations():
    with connect() as c: return [{'id': r[0], **json.loads(r[1])} for r in c.execute('SELECT id,payload FROM observations ORDER BY created DESC')]

@app.get('/api/observations/{id}/original.csv')
def observation_original(id: str):
    with connect() as c:
        if not c.execute('SELECT 1 FROM observations WHERE id=?',(id,)).fetchone(): raise HTTPException(404, 'Observation dataset not found')
    return FileResponse(DATA/'observations'/id/'original.csv', filename='citylab-original-observations.csv')

@app.post('/api/calibrations', status_code=202)
def calibrate(spec: CalibrationSpec):
    id = new_task('calibration', spec.model_dump())
    try: launch('calibration', id)
    except HTTPException as e: update_task(id, 'failed', error=e.detail); raise
    return gettask(id)

@app.get('/api/jobs/{id}/bundle.zip')
def run_bundle(id: str):
    value=getjob(id)
    if value['status'] in ('queued','running','cancelling'): raise HTTPException(409,'Wait for completion or cancel before exporting a stable run bundle')
    import zipfile
    output = DATA/'jobs'/id/'export.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('job-state.json',json.dumps(value,indent=2))
        for p in (DATA/'jobs'/id).rglob('*'):
            if p.is_file() and p != output and p.suffix != '.tmp': z.write(p, p.relative_to(output.parent))
    setting('exported:'+id, True)
    return FileResponse(output, filename='citylab-run-'+id+'.zip')

@app.delete('/api/jobs/{id}')
def delete_run(id: str):
    value = getjob(id)
    if value['status'] in ('queued','running','cancelling'): raise HTTPException(409, 'Cancel the active run before deleting')
    if not setting('exported:'+id): raise HTTPException(409, 'Export the reproducibility ZIP before deleting this run')
    # Keep studies reproducible: their referenced trials cannot be deleted individually.
    with connect() as c:
        if c.execute('SELECT 1 FROM tasks WHERE ? LIKE id || ?', (id, '-%')).fetchone(): raise HTTPException(409, 'This run belongs to a study; retain it with its evidence')
        c.execute('DELETE FROM jobs WHERE id=?', (id,))
    shutil.rmtree(DATA/'jobs'/id)
    return {'deleted': True}

@app.get('/api/demo')
def demo():
    path = ROOT/'examples/case-study/index.json'
    return json.loads(path.read_text()) if path.exists() else {'available': False, 'message': 'Generate the documented case study with python -m scripts.build_demo'}

if (ROOT/'frontend/dist').exists(): app.mount('/', StaticFiles(directory=ROOT/'frontend/dist', html=True), name='frontend')
