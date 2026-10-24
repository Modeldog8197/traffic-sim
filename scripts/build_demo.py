"""Generate genuine SUMO evidence; cached completed trials make this resumable."""
import csv,io,json,shutil,time
from pathlib import Path
from backend.network import DATA,ROOT,describe,ensure_synthetic
from backend.models import Scenario,ExperimentSpec,SearchSpace,TransitLine,BusStop
from backend.engine import execute
from backend.frames import atomic_json
from backend.store import connect,task
from backend.explorer import plan,run_experiment
from backend.calibration import CalibrationSpec,run_calibration
from backend.imports import parse_observations

def register_run(id,s):
    folder=DATA/'jobs'/id
    if (folder/'result.json').exists(): return json.loads((folder/'result.json').read_text())
    r=execute(s,folder)
    with connect() as c:c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?)',(id,'completed',1,s.model_dump_json(),None,time.time()))
    print(id,r['metrics']['completed'],r['metrics']['mean'],flush=True)
    return r

def register_task(id,kind,spec):
    folder=DATA/'tasks'/id;folder.mkdir(parents=True,exist_ok=True)
    with connect() as c:c.execute('INSERT OR IGNORE INTO tasks VALUES (?,?,?,?,?,?,?,?)',(id,kind,'queued',0,spec.model_dump_json(),'{}',None,time.time()))
    return folder

def main():
    ensure_synthetic()
    s=Scenario(name='Recorded case · fixed 30 s',duration=120,clearance=180,demand=160,seed=42,transit=[TransitLine(id='B1',route=['n01_n11','n11_n21','n21_n31','n31_n32','n32_n33'],stops=[BusStop(edge='n11_n21',position=110,dwell=15)],headway=30)],corridors={'Eastbound north':['n00_n10','n10_n20','n20_n30']})
    baseline=register_run('demo-v2b-baseline',s)
    intervention=register_run('demo-v2b-timing',s.model_copy(update={'name':'Recorded case · fixed 15 s','green':15}))
    pressure=register_run('demo-v2b-pressure',s.model_copy(update={'name':'Recorded case · movement pressure','controller':'pressure','transit_extension':5}))
    spec=ExperimentSpec(name='Recorded research · five demand conditions',scenario=s,mode='research',space=SearchSpace(greens=[15,30],controllers=['fixed','pressure'],transit_extensions=[5]),max_candidates=4,finalists=2,budget=370,search_seeds=[11,12],tuning_seeds=[31,32],evaluation_seeds=list(range(101,111)),conditions=['uniform','peak','high_demand','bus_mix','disruption'],disruption_road='n11_n21',min_completion=.5,max_completion_drop=.05,ablations=True)
    folder=register_task('demo-v2b-research','experiment',spec)
    if not (folder/'plan.json').exists():atomic_json(folder/'plan.json',plan(spec))
    if task('demo-v2b-research')['status']!='completed':run_experiment('demo-v2b-research')
    if task('demo-v2b-research')['status']!='completed':raise RuntimeError(task('demo-v2b-research'))
    controller_spec=ExperimentSpec(name='Recorded controller ablation · pressure and priority',scenario=s,mode='research',space=SearchSpace(greens=[],controllers=['pressure'],transit_extensions=[5]),max_candidates=1,finalists=1,budget=220,search_seeds=[11,12],tuning_seeds=[31,32],evaluation_seeds=list(range(101,111)),conditions=['uniform','peak','high_demand','bus_mix','disruption'],disruption_road='n11_n21',min_completion=.5,max_completion_drop=.05,ablations=True)
    controller_folder=register_task('demo-v2b-controller-study','experiment',controller_spec)
    if not (controller_folder/'plan.json').exists():atomic_json(controller_folder/'plan.json',plan(controller_spec))
    if task('demo-v2b-controller-study')['status']!='completed':run_experiment('demo-v2b-controller-study')
    if task('demo-v2b-controller-study')['status']!='completed':raise RuntimeError(task('demo-v2b-controller-study'))
    fixture=Scenario(name='Synthetic observation generator',duration=120,clearance=60,demand=100,seed=9)
    fr=register_run('demo-v2b-observation-source',fixture)
    rows=[]
    roads=['n00_n10','n10_n20','n11_n21','n22_n32','n33_n23','n01_n11']
    for road in roads:
        for start,end in [(0,60),(60,120),(120,180)]:
            entries=[e for e in fr['edge_crossings'] if e['road_id']==road and start<=e['time']<end]
            rows.append([road,start,end,len(entries),sum(e['speed_mps'] for e in entries)/len(entries) if entries else '', 'all'])
    out=io.StringIO();w=csv.writer(out);w.writerow(['road_id','start_s','end_s','vehicle_count','mean_speed_mps','vehicle_class']);w.writerows(rows)
    raw=out.getvalue().encode(); obs=parse_observations(raw,'synthetic');obs['provenance']='Synthetic fixture · SUMO seed 9 · not field observations'
    obfolder=DATA/'observations'/'demo-v2b-synthetic';obfolder.mkdir(parents=True,exist_ok=True);(obfolder/'original.csv').write_bytes(raw)
    with connect() as c:c.execute('INSERT OR REPLACE INTO observations VALUES (?,?,?,?)',('demo-v2b-synthetic','synthetic',json.dumps(obs),time.time()))
    cs=CalibrationSpec(observation_id='demo-v2b-synthetic',scenario=fixture,demand_values=[80,100,120],bus_fractions=[.08],fit_end=60,validation_start=60)
    cf=register_task('demo-v2b-calibration','calibration',cs)
    if task('demo-v2b-calibration')['status']!='completed':run_calibration('demo-v2b-calibration')
    if task('demo-v2b-calibration')['status']!='completed':raise RuntimeError(task('demo-v2b-calibration'))
    outdir=ROOT/'examples/case-study';outdir.mkdir(parents=True,exist_ok=True)
    records=json.loads((folder/'result.json').read_text())['records']+json.loads((controller_folder/'result.json').read_text())['records'];ids=[r['run_id'] for r in records]+['demo-v2b-baseline','demo-v2b-timing','demo-v2b-pressure','demo-v2b-observation-source']
    bundle=outdir/'data'
    for id in ids:shutil.copytree(DATA/'jobs'/id,bundle/'jobs'/id,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.log','export.zip'))
    for id in ['demo-v2b-research','demo-v2b-controller-study','demo-v2b-calibration']:shutil.copytree(DATA/'tasks'/id,bundle/'tasks'/id,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.log','*.zip'))
    shutil.copytree(obfolder,bundle/'observations'/'demo-v2b-synthetic',dirs_exist_ok=True)
    with connect() as c:
        tables={}
        for table in ['jobs','tasks','observations']:
            cur=c.execute('SELECT * FROM '+table+" WHERE id LIKE 'demo-v2b-%'");tables[table]={'columns':[d[0] for d in cur.description],'rows':[list(r) for r in cur.fetchall()]}
    atomic_json(outdir/'catalog.json',tables)
    bm,im=baseline['metrics'],intervention['metrics']
    finding=f"Seed 42, fixed 30 → 15 s: completed {bm['completed']} → {im['completed']} of {s.demand}; completed-trip mean {bm['mean']:.1f} → {im['mean']:.1f} s; full-demand loss {bm['full_demand_loss']:.1f} → {im['full_demand_loss']:.1f} s/request. These are simulated outcomes, not measured Bangalore traffic."
    atomic_json(outdir/'index.json',{'available':True,'baseline':'demo-v2b-baseline','intervention':'demo-v2b-timing','controller':'demo-v2b-pressure','study':'demo-v2b-research','calibration':'demo-v2b-calibration','report_url':'/api/tasks/demo-v2b-research/report.html','finding':finding})
    atomic_json(outdir/'study-spec.json',spec.model_dump());atomic_json(outdir/'baseline.json',s.model_dump());(outdir/'synthetic-observations.csv').write_bytes(raw)
    print(finding,flush=True)
if __name__=='__main__':main()
