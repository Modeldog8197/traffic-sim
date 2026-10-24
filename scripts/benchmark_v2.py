"""Comparable input workload; new measurement model is explicitly identified."""
import json,time,resource,platform,statistics
from pathlib import Path
from backend.engine import execute
from backend.models import Scenario
from backend.frames import page

def main():
    records=[]
    for detailed in [True,False]:
        folder=Path('data/benchmark-v2-'+('recorded' if detailed else 'aggregate'))
        r=execute(Scenario(duration=600,clearance=180,demand=1000,seed=42),folder,record=detailed)
        retrieval=[]
        if detailed:
            for i in range(80):
                t=time.perf_counter();page(folder,(i*17)%370,32);retrieval.append((time.perf_counter()-t)*1000)
        records.append({'recorded':detailed,'wall_seconds':r['wall_seconds'],'horizon_s':780,'requested_vehicles':1000,'trajectory_bytes':sum(p.stat().st_size for p in (folder/'frames').glob('*')),'decision_log_bytes':(folder/'decisions.ndjson').stat().st_size if detailed else 0,'retrieval_32_frames_ms_median':statistics.median(retrieval) if retrieval else None,'retrieval_32_frames_ms_p95':sorted(retrieval)[75] if retrieval else None,'python_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'child_peak_rss_bytes':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'metrics':r['metrics'],'engine':r['engine']})
    legacy=Path('data/benchmark/frames.ndjson')
    retrieval=[]
    if legacy.exists():
        for i in range(30):
            t=time.perf_counter();lines=legacy.read_text().splitlines();frames=[json.loads(l) for l in lines[(i*11)%350:][:32]];retrieval.append((time.perf_counter()-t)*1000)
    report={'platform':platform.platform(),'workload':{'network':'synthetic 48 directed roads','demand':1000,'seed':42,'duration':600,'clearance':180,'step':.5},'before':json.loads(Path('docs/upgrade-before-1000.json').read_text()),'after':records,'legacy_32_frames_ms_median':statistics.median(retrieval) if retrieval else None,'note':'Same documented input workload, but v2 uses named independent demand streams, explicit transit semantics and richer metrics. Simulation timing is not an isolated algorithm-speed comparison. RSS includes separate Python and terminated SUMO child peaks, not concurrent total memory; browser measurements are separate.'}
    Path('docs/benchmark-v2.json').write_text(json.dumps(report,indent=2));print(json.dumps([{k:v for k,v in r.items() if k!='metrics'} for r in records],indent=2))
if __name__=='__main__':main()
