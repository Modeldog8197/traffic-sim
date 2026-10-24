import copy,json,time
import pytest
from fastapi.testclient import TestClient
from backend.api import app,recover
from backend.models import Scenario,ExperimentSpec,SearchSpace,TransitLine,BusStop
from backend.network import describe,DATA
from backend.demand import manifest
from backend.frames import FrameWriter,page
from backend.comparison import compare
from backend.explorer import plan,condition,summarize_candidates
from backend.statistics import nondominated
from backend.imports import parse_observations
from backend.calibration import CalibrationSpec,residuals
from backend.store import connect,task
from backend.engine import execute


def test_version_migration():
    assert Scenario(**{'schema_version':1,'name':'old'}).schema_version==2
    assert Scenario(name='old').name=='old'
    with pytest.raises(ValueError):Scenario(schema_version=3)

def test_frame_chunks_and_legacy(tmp_path):
    w=FrameWriter(tmp_path)
    for i in range(97):w.append({'time':(i+1)*2,'vehicles':[{'id':str(i)}]})
    assert len(list((tmp_path/'frames').glob('*.gz')))==4
    batch=page(tmp_path,30,5)
    assert [f['time'] for f in batch['frames']]==[62,64,66,68,70]
    assert batch['next']==35 and batch['total']==97
    assert page(tmp_path,200,64)['frames']==[]
    legacy=tmp_path/'legacy';legacy.mkdir();(legacy/'frames.ndjson').write_text('{"time":2}\n{"time":4}\n')
    assert page(legacy)['total']==2 and (legacy/'frames.ndjson').exists()

def test_protocol_and_budget():
    s=Scenario(duration=60,demand=10)
    with pytest.raises(ValueError):ExperimentSpec(scenario=s,evaluation_seeds=[11])
    with pytest.raises(ValueError):ExperimentSpec(scenario=s,mode='research')
    spec=ExperimentSpec(scenario=s,budget=200,space=SearchSpace(greens=[15],controllers=['fixed'],transit_extensions=[0]))
    a=plan(spec);assert a==plan(spec) and len(a['candidates'])==2
    assert a['maximum_runs']<=spec.budget
    with pytest.raises(ValueError):plan(spec.model_copy(update={'budget':4}))
    for c in a['candidates']:
        assert c['scenario']['demand']==10 and c['scenario']['network']=='synthetic'

def test_pareto_excludes_unserved_candidate():
    rows=[{'id':'a','feasible':True,'metrics':{'loss':100,'co2':5}}, {'id':'b','feasible':False,'metrics':{'loss':1,'co2':1}}, {'id':'c','feasible':True,'metrics':{'loss':110,'co2':6}}]
    assert nondominated(rows,['loss','co2'])==['a']

def test_observation_validation():
    header='road_id,start_s,end_s,vehicle_count,mean_speed_mps,vehicle_class\n'
    raw=(header+'n00_n10,0,60,4,3.2,all\n').encode()
    p=parse_observations(raw,'synthetic');assert p['rows'][0]['vehicle_count']==4
    for bad in ['missing,0,60,4,3.2,all\n','n00_n10,0,60,-1,3.2,all\n','n00_n10,60,0,4,3.2,all\n','n00_n10,0,60,4,nan,all\n','n00_n10,0,60,,3.2,all\n','n00_n10,0,60,4,3.2,all\nn00_n10,30,90,2,3,passenger\n']:
        with pytest.raises(ValueError):parse_observations((header+bad).encode(),'synthetic')

def test_calibration_separation_and_units():
    s=Scenario(duration=120)
    with pytest.raises(ValueError):CalibrationSpec(observation_id='x',scenario=s,fit_end=61,validation_start=60)
    with pytest.raises(ValueError):CalibrationSpec(observation_id='x',scenario=s,validation_seeds=[11])
    rows=[{'road_id':'a','start_s':0,'end_s':10,'vehicle_class':'all','vehicle_count':2,'mean_speed_mps':4}]
    result={'edge_crossings':[{'road_id':'a','time':0,'vehicle_class':'passenger','speed_mps':3},{'road_id':'a','time':10,'vehicle_class':'passenger','speed_mps':6}]}
    r=residuals(rows,result);assert r['count_mae']==1 and r['rows'][0]['speed_residual']==-1

def test_explicit_transit_preserved_and_validated():
    line=TransitLine(id='T',route=['n00_n10','n10_n20'],stops=[BusStop(edge='n10_n20',position=100)],headway=30)
    s=Scenario(duration=60,demand=20,transit=[line]);a=manifest(s)
    buses=[t for t in a if t['kind']=='bus'];assert len(buses)==2
    assert all(t['stops'][0]['edge']=='n10_n20' for t in buses)
    assert manifest(s.model_copy(update={'green':15}))==a
    with pytest.raises(ValueError):manifest(s.model_copy(update={'transit':[line.model_copy(update={'route':['n00_n10','n33_n23']})]}))

def test_stable_scenario_rename_and_duplicate():
    # Avoid lifespan restart recovery while independent studies are executing.
    c=TestClient(app)
    s=Scenario(name='First').model_dump()
    assert c.put('/api/scenarios/release-test-original',json=s).status_code==200
    assert c.put('/api/scenarios/release-test-original',json={**s,'name':'Renamed'}).status_code==200
    c.put('/api/scenarios/release-test-copy',json={**s,'name':'Renamed copy'})
    rows=c.get('/api/scenarios').json()
    assert next(r for r in rows if r['id']=='release-test-original')['name']=='Renamed'
    c.delete('/api/scenarios/release-test-copy');assert any(r['id']=='release-test-original' for r in c.get('/api/scenarios').json())
    c.delete('/api/scenarios/release-test-original')

def test_held_out_condition_service_match():
    s=Scenario(duration=60,demand=20);spec=ExperimentSpec(scenario=s,disruption_road='n11_n21')
    for name in ['uniform','peak','high_demand','bus_mix','disruption']:
        a=condition(s.model_dump(),name,spec,101);b=condition(s.model_copy(update={'green':15}).model_dump(),name,spec,101)
        assert manifest(a)==manifest(b)

def test_historical_network_and_rejection():
    # Authentic bundled case data when generated; small isolated fixture otherwise.
    a={'network':{'version':'network-A'},'manifest_hash':'m','metrics':{'horizon':120,'warmup':0,'requested':10,'completed':8,'completion_rate':.8,'sample_size':8},'measurement_version':2,'engine':'SUMO test','scenario':{'warmup':0,'routing':'departure_fastest','car_occupancy':1.5,'bus_occupancy':30}}
    assert compare(a,a)['compatible']
    b=copy.deepcopy(a);b['network']['version']='network-B';assert not compare(a,b)['compatible']
    b=copy.deepcopy(a);b['manifest_hash']='other';assert not compare(a,b)['compatible']
    b=copy.deepcopy(a);b['measurement_version']=1;assert not compare(a,b)['compatible']

@pytest.mark.integration
def test_pressure_recording_matches_aggregate_and_transitions(tmp_path):
    s=Scenario(duration=61,clearance=60,demand=35,controller='pressure',transit_extension=3)
    a=execute(s,tmp_path/'record');b=execute(s,tmp_path/'aggregate',record=False)
    assert a['metrics']==b['metrics'] and a['manifest_hash']==b['manifest_hash']
    assert not (tmp_path/'aggregate'/'frames').exists()
    decisions=[json.loads(l) for l in (tmp_path/'record'/'decisions.ndjson').read_text().splitlines()]
    assert decisions
    for d in [d for row in decisions for d in row['junctions'].values()]:
        moves=d['movements'];assert len({(m['incoming'],m['outgoing']) for m in moves})==len(moves)
        if 'y' in d['state'] or not any(c in 'Gg' for c in d['state']):assert d['action']=='preserve'
        if d['elapsed']<s.min_green and any(c in 'Gg' for c in d['state']) and 'y' not in d['state']:assert d['action']=='extend'
        if d['elapsed']>=s.max_green and any(c in 'Gg' for c in d['state']) and 'y' not in d['state']:assert d['action']=='end'
        assert d['priority_used']<=s.transit_extension+.5
    assert a['metrics']['co2_kg']>0 and a['metrics']['full_demand_loss']>=a['metrics']['mean']
    assert page(tmp_path/'record',60,5)['frames'][-1]['time']==121

def test_restart_and_partial_results(tmp_path,monkeypatch):
    import backend.api as api_module
    import backend.store as store
    monkeypatch.setattr(store,'DATA',tmp_path)
    monkeypatch.setattr(api_module,'DATA',tmp_path)
    with store.connect() as c:
        c.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)',('recover-test','experiment','running',.5,'{}','{"completed_runs":2}',None,0))
        c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?)',('job-test','running',.5,Scenario().model_dump_json(),None,0))
    api_module.recover()
    assert store.task('recover-test')['status']=='interrupted'
    assert store.job('job-test')['status']=='interrupted'
    with pytest.raises(Exception) as error:api_module.task_result('recover-test')
    assert error.value.status_code==409

def test_resume_preserves_completed_checkpoint(tmp_path,monkeypatch):
    import backend.explorer as ex
    import backend.store as store
    from backend.frames import atomic_json
    monkeypatch.setattr(store,'DATA',tmp_path);monkeypatch.setattr(ex,'DATA',tmp_path)
    spec=ExperimentSpec(scenario=Scenario(duration=60,demand=10),space=SearchSpace(greens=[15],controllers=['fixed'],transit_extensions=[0]),search_seeds=[11],tuning_seeds=[31],evaluation_seeds=[101],conditions=['uniform'],ablations=False,budget=20)
    folder=tmp_path/'tasks'/'resume';folder.mkdir(parents=True)
    with store.connect() as c:c.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)',('resume','experiment','queued',0,spec.model_dump_json(),'{}',None,0))
    atomic_json(folder/'plan.json',ex.plan(spec))
    calls=[]
    def fake(s,path,**kwargs):
        calls.append(s.name)
        if len(calls)==2:raise InterruptedError('simulated interruption')
        m={k:1 for k in ex.METRICS};m.update(completion_rate=1,invalid=0,requested=10,horizon=240,sample_size=10)
        result={'metrics':m,'manifest_hash':'matched','network':{'version':'n'},'groups':[],'scenario':s.model_dump(),'engine':'SUMO fixture','measurement_version':2}
        atomic_json(path/'result.json',result);return result
    monkeypatch.setattr(ex,'execute',fake);ex.run_experiment('resume')
    assert store.task('resume')['status']=='cancelled'
    cp=json.loads((folder/'checkpoint.json').read_text());assert len(cp)==1
    ex.run_experiment('resume')
    assert store.task('resume')['status']=='completed'
    assert len(calls)==7 # one interrupted attempt + six unique trials
    report=json.loads((folder/'result.json').read_text());assert report['completed_runs']==6
    assert (folder/'frozen.json').exists()

@pytest.mark.integration
def test_deterministic_across_python_hash_seeds(tmp_path):
    import subprocess,sys,os
    script='from pathlib import Path;from backend.engine import execute;from backend.models import Scenario;execute(Scenario(duration=60,clearance=60,demand=20,controller="pressure"),Path(__import__("sys").argv[1]))'
    for seed in ['1','2']:
        subprocess.run([sys.executable,'-c',script,str(tmp_path/seed)],env={**os.environ,'PYTHONHASHSEED':seed},check=True,capture_output=True)
    a=json.loads((tmp_path/'1/result.json').read_text());b=json.loads((tmp_path/'2/result.json').read_text())
    assert a['metrics']==b['metrics'] and a['completed_trips']==b['completed_trips']

def test_rerun_metric_tolerance_is_bounded():
    from backend.playback_jobs import metrics_match
    assert metrics_match({'co2_kg':1.,'completed':10},{'co2_kg':1.+1e-12,'completed':10})
    assert not metrics_match({'co2_kg':1.,'completed':10},{'co2_kg':1.1,'completed':10})
    assert not metrics_match({'completed':10},{'completed':9})

def test_concurrent_legacy_frame_migration(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    (tmp_path/'frames.ndjson').write_text(''.join(json.dumps({'time':2*(i+1)})+'\n' for i in range(100)))
    with ThreadPoolExecutor(2) as pool:
        a,b=list(pool.map(lambda _:page(tmp_path,0,128),range(2)))
    assert a==b and a['total']==100 and len(a['frames'])==100
