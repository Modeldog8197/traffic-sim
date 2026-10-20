"""Recoverable deterministic detailed reruns of an already matched pair."""
import json,time,math
from .network import DATA
from .store import task,connect,update_task,update_job
from .models import Scenario
from .engine import execute
from .frames import atomic_json
from .comparison import compare

def record_pair(id):
    folder=DATA/'tasks'/id;spec=task(id)['spec'];results={}
    try:
        for i,key in enumerate(['baseline','candidate']):
            if (folder/'cancel').exists():raise InterruptedError('Playback recording cancelled')
            original=json.loads((DATA/'jobs'/spec[key]/'result.json').read_text());run_id=id+'-'+key;target=DATA/'jobs'/run_id
            s=Scenario(**original['scenario']);s.network_version=original['network']['version']
            if (target/'result.json').exists():r=json.loads((target/'result.json').read_text())
            else:
                target.mkdir(parents=True,exist_ok=True)
                with connect() as c:c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?)',(run_id,'running',0,s.model_dump_json(),None,time.time()))
                update_task(id,'running',i/2,{'stage':'Recording '+key,'completed_runs':i})
                try:r=execute(s,target,trip_manifest=original['manifest'],cancelled=lambda:(folder/'cancel').exists(),record=True)
                except InterruptedError:update_job(run_id,'cancelled',error='Parent task cancelled');raise
                except Exception as e:update_job(run_id,'failed',error=str(e));raise
                if not metrics_match(r['metrics'],original['metrics']):raise ValueError('Detailed rerun differs from source metrics; evidence was not substituted.')
                update_job(run_id,'completed',1)
            results[key]=run_id
        check=compare(*[json.loads((DATA/'jobs'/results[k]/'result.json').read_text()) for k in ['baseline','candidate']])
        if not check['compatible']:raise ValueError('Rerun pair is incompatible')
        atomic_json(folder/'result.json',results);update_task(id,'completed',1,{'stage':'Recorded pair ready','completed_runs':2})
    except InterruptedError as e:update_task(id,'cancelled',error=str(e))
    except Exception as e:update_task(id,'failed',error=str(e))


def metrics_match(a,b):
    """Account for sub-nanounit floating summation differences in old v2 files."""
    return set(a)==set(b) and all(math.isclose(a[k],b[k],rel_tol=1e-12,abs_tol=1e-9) if isinstance(a[k],(int,float)) and isinstance(b[k],(int,float)) else a[k]==b[k] for k in a)
