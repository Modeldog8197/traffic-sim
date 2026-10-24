import time
from fastapi.testclient import TestClient
from backend.api import app
from backend.models import Scenario


def wait(client,id):
    until=time.time()+30
    while time.time()<until:
        j=client.get('/api/jobs/'+id).json()
        if j['status'] not in ('queued','running','cancelling'):return j
        time.sleep(.1)
    raise AssertionError('Job timeout')

def test_save_import_export_delete():
    with TestClient(app) as c:
        s=Scenario(name='API roundtrip').model_dump()
        assert c.put('/api/scenarios/test',json=s).status_code==200
        rows=c.get('/api/scenarios').json();assert any(r['name']==s['name'] for r in rows)
        assert c.post('/api/validate',json=s).json()['valid']
        assert c.post('/api/validate',json={**s,'green':0}).status_code==422
        assert c.delete('/api/scenarios/test').status_code==200
        assert not any(r['id']=='test' for r in c.get('/api/scenarios').json())

def test_job_cancel_recover_and_export():
    with TestClient(app) as c:
        s=Scenario(duration=600,demand=500).model_dump()
        j=c.post('/api/jobs',json=s).json();assert j['id']
        assert c.post('/api/jobs/'+j['id']+'/cancel').status_code==200
        assert wait(c,j['id'])['status']=='cancelled'
        j=c.post('/api/jobs',json=Scenario(duration=60,clearance=60,demand=10).model_dump()).json()
        assert wait(c,j['id'])['status']=='completed'
        r=c.get('/api/jobs/'+j['id']+'/export.json').json()
        assert r['engine'].startswith('SUMO') and r['manifest_hash']
        assert 'completion_rate' in c.get('/api/jobs/'+j['id']+'/export.csv').text
        assert c.get('/api/jobs/'+j['id']+'/frames').json()['frames']
