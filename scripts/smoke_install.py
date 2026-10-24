"""Exercise startup and an actual engine job in a chosen CITYLAB_DATA directory."""
import time,json
from fastapi.testclient import TestClient
from backend.api import app

def main():
    with TestClient(app) as client:
        assert client.get('/api/health').json()['available']
        demo=client.get('/api/demo').json();assert demo['available']
        result=client.get('/api/jobs/'+demo['baseline']+'/result');assert result.status_code==200
        assert client.get('/api/jobs/'+demo['baseline']+'/frames?offset=32&limit=5').json()['frames']
        task=client.post('/api/jobs',json={'duration':60,'clearance':60,'demand':5,'name':'Clean-install smoke'}).json()
        for _ in range(600):
            state=client.get('/api/jobs/'+task['id']).json()
            if state['status'] not in ('queued','running','cancelling'):break
            time.sleep(.1)
        assert state['status']=='completed',state
        r=client.get('/api/jobs/'+task['id']+'/result').json();assert r['metrics']['requested']==5
        print(json.dumps({'startup':'passed','bundled_recording':'passed','engine_job':'completed','engine':r['engine'],'metrics':r['metrics']},indent=2))
if __name__=='__main__':main()
