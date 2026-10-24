import json
import pytest,sumolib
from backend.models import Scenario,RoadEdit
from backend.network import net_path
from backend.demand import manifest,digest
from backend.routing import validate_network
from backend.metrics import percentile,summarize
from backend.engine import execute
from backend.frames import page
def read_frames(folder):
    result=[]; offset=0
    while True:
        batch=page(folder,offset,128);result.extend(batch["frames"]);offset=batch["next"]
        if offset>=batch["total"]:return result

def test_validation():
    with pytest.raises(ValueError):Scenario(warmup=600)
    with pytest.raises(ValueError):Scenario(green=2)
    with pytest.raises(ValueError):RoadEdit(speed=0)
    with pytest.raises(ValueError):RoadEdit(allowed=['helicopter'])
def test_manifest_and_roundtrip():
    s=Scenario();assert manifest(s)==manifest(s)
    assert digest(manifest(s))==digest(manifest(s.model_copy(update={'roads':{'n11_n21':RoadEdit(closed=True)}})))
    assert Scenario.model_validate_json(s.model_dump_json())==s

def test_closure():
    net=sumolib.net.readNet(str(net_path()));s=Scenario();trips=manifest(s)
    base,_=validate_network(s,trips,net)
    s.roads={'n11_n21':RoadEdit(closed=True)};routes,invalid=validate_network(s,trips,net)
    assert all('n11_n21' not in r for r in routes.values() if r)
    assert any(r and base[k]!=r for k,r in routes.items())
    s.roads={e.getID():RoadEdit(closed=True) for e in net.getEdges()}
    with pytest.raises(ValueError,match='All trips'):validate_network(s,trips,net)

def test_metrics():
    assert percentile([10,20,30,40],.95)==38.5
    assert percentile([],.95) is None
    rows=[{'travel_time':20,'delay':10,'kind':'bus','depart':0},{'travel_time':40,'delay':20,'kind':'passenger','depart':10}]
    m=summarize([1,2,3,4],rows,1,0,1,100,0,[])
    assert m['mean']==30 and m['completion_rate']==.5 and m['throughput']==72
    assert m['requested']==m['completed']+m['active']+m['backlog']+m['invalid']

@pytest.mark.integration
def test_sumo_reproducible_and_closure(tmp_path):
    s=Scenario(duration=60,clearance=120,demand=40)
    a=execute(s,tmp_path/'a');b=execute(s,tmp_path/'b')
    assert a['metrics']==b['metrics']
    assert a['completed_trips']==b['completed_trips']
    c=execute(s.model_copy(update={'roads':{'n11_n21':RoadEdit(closed=True)}}),tmp_path/'c')
    assert a['manifest_hash']==c['manifest_hash']
    assert all('n11_n21' not in r for r in c['routes'].values() if r)
    for r in [a,b,c]:
        m=r['metrics'];assert m['requested']==m['completed']+m['active']+m['backlog']+m['invalid']
        assert m['completed']>0
    frames=read_frames(tmp_path/'a')
    assert frames[1]['time']-frames[0]['time']==2
    assert any(f['vehicles'] for f in frames)
    for f in frames:
        counts=f['counts'];assert counts['requested']==sum(counts[k] for k in ['scheduled','active','completed','backlog','invalid','otherwise_unserved'])

@pytest.mark.integration
def test_cancel(tmp_path):
    with pytest.raises(InterruptedError):execute(Scenario(duration=60,demand=20),tmp_path/'cancel',cancelled=lambda:True)
    assert execute(Scenario(duration=60,clearance=60,demand=5),tmp_path/'recovery')['metrics']['requested']==5

@pytest.mark.integration
def test_responsive_changes_phase_without_starvation(tmp_path):
    execute(Scenario(duration=120,clearance=60,demand=40,controller='responsive'),tmp_path/'signals')
    frames=read_frames(tmp_path/'signals')
    for jid in frames[0]['signals']:
        states=[f['signals'][jid] for f in frames]
        assert len(set(states))>=4
        streak=0;old=None
        for state in states:
            streak=streak+2 if state==old else 2;old=state
            if 'G' in state or 'g' in state:assert streak<=62

def test_custom_od_and_signal_validation():
    from backend.models import ODPair
    s=Scenario(demand=20,od=[ODPair(origin='n00_n10',destination='n23_n33')],signals={'n11':{0:20}})
    trips=manifest(s)
    assert all(t['from']=='n00_n10' and t['to']=='n23_n33' for t in trips)
    validate_network(s,trips,sumolib.net.readNet(str(net_path())))
    s.signals={'n11':{1:20}}
    with pytest.raises(ValueError,match='editable green'):validate_network(s,trips,sumolib.net.readNet(str(net_path())))

@pytest.mark.integration
def test_phase_override_affects_engine(tmp_path):
    s=Scenario(duration=60,clearance=60,demand=15,signals={'n11':{0:10}})
    execute(s,tmp_path/'override')
    frames=read_frames(tmp_path/'override')
    states=[f['signals']['n11'] for f in frames]
    assert states[0]!=states[6] # 10-second initial green already ended by 14 s

@pytest.mark.integration
def test_odd_horizon_final_accounting(tmp_path):
    r=execute(Scenario(duration=61,clearance=60,demand=17),tmp_path/'odd')
    frames=read_frames(tmp_path/'odd')
    assert frames[-1]['time']==121
    m=r['metrics'];assert m['requested']==m['completed']+m['active']+m['backlog']+m['invalid']
    assert m['completed']==frames[-1]['counts']['completed']
