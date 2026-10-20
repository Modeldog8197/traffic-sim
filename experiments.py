"""Bounded, sequential matched-seed research runner; each SUMO execution isolated."""
import argparse,json,statistics,math,multiprocessing,platform,time
from pathlib import Path
from .models import Scenario
from .engine import execute

def _run(payload,folder):execute(Scenario(**payload),Path(folder))
def isolated(s,folder):
    p=multiprocessing.get_context('spawn').Process(target=_run,args=(s.model_dump(),str(folder)))
    p.start();p.join(300)
    if p.is_alive():p.terminate();p.join();raise RuntimeError('Run exceeded 300 s wall-time budget')
    if p.exitcode:raise RuntimeError(f'Run failed: {folder}')
    return json.loads((folder/'result.json').read_text())
def aggregate(values):
    n=len(values);mean=statistics.mean(values)
    sd=statistics.stdev(values) if n>1 else None
    # Student t quantiles, df 1..9; sufficient for default n=3.
    critical={1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262}.get(n-1)
    half=critical*sd/math.sqrt(n) if sd is not None and critical else None
    return {'n':n,'mean':mean,'run_sd':sd,'mean_95_ci':[mean-half,mean+half] if half is not None else None,'interval':'Student t; independent seed runs; unadjusted exploratory interval'}
def research(out):
    out.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    base=Scenario(duration=120,clearance=180,demand=100,bus_fraction=.1)
    training=[]
    # 6 training simulations; fixed grid, deterministic tie-break toward shorter green.
    for green in [15,30,45]:
        scores=[]
        for seed in [11,12]:
            s=base.model_copy(update={'green':green,'seed':seed,'pattern':'uniform'})
            r=isolated(s,out/f'train-{green}-{seed}');m=r['metrics']
            score=(m['delay'] or 0)+m['horizon']*(1-m['completion_rate'])
            scores.append(score)
        training.append({'green':green,'score':statistics.mean(scores)})
    chosen=min(training,key=lambda r:(r['score'],r['green']))['green'];evaluation=[]
    for seed in [101,102,103]:
        for label,control,green in [('baseline','fixed',30),('tuned','fixed',chosen),('responsive','responsive',30)]:
            s=base.model_copy(update={'seed':seed,'pattern':'peak','green':green,'controller':control,'name':label})
            r=isolated(s,out/f'eval-{label}-{seed}');evaluation.append({'label':label,'seed':seed,'manifest_hash':r['manifest_hash'],'metrics':r['metrics'],'junction_waiting_seconds':r['junction_waiting_seconds'],'engine':r['engine'],'network_version':r['network']['version']})
    summaries={};deltas={}
    for label in ['baseline','tuned','responsive']:
        rows=[r for r in evaluation if r['label']==label]
        summaries[label]={key:aggregate([r['metrics'][key] for r in rows if r['metrics'][key] is not None]) for key in ['delay','mean','p95','completion_rate','bus_mean','car_mean'] if any(r['metrics'][key] is not None for r in rows)}
        if label!='baseline':
            pairs=[(r,next(b for b in evaluation if b['label']=='baseline' and b['seed']==r['seed'])) for r in rows]
            assert all(a['manifest_hash']==b['manifest_hash'] for a,b in pairs)
            deltas[label]={key:aggregate([a['metrics'][key]-b['metrics'][key] for a,b in pairs if a['metrics'][key] is not None and b['metrics'][key] is not None]) for key in ['delay','completion_rate','bus_mean','car_mean'] if any(a['metrics'][key] is not None and b['metrics'][key] is not None for a,b in pairs)}
    report={'base_scenario':base.model_dump(),'training_seeds':[11,12],'evaluation_seeds':[101,102,103],'training_pattern':'uniform','evaluation_pattern':'peak','budget':{'training_runs':6,'evaluation_runs':9,'candidates':[15,30,45]},'training':training,'chosen_green':chosen,'evaluation':evaluation,'summaries':summaries,'paired_deltas':deltas,'wall_seconds':time.perf_counter()-start,'hardware':platform.platform(),'limitation':'Three evaluation seeds on one synthetic grid and held-out peak pattern; exploratory evidence only.'}
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'chosen_green':chosen,'summaries':summaries,'wall_seconds':report['wall_seconds']},indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('data/research'));args=parser.parse_args();research(args.output)
