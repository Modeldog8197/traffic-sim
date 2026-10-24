import math, statistics

def percentile(xs,p):
    if not xs:return None
    xs=sorted(xs); k=(len(xs)-1)*p; lo=int(k); hi=math.ceil(k)
    return xs[lo]+(xs[hi]-xs[lo])*(k-lo)

def summarize(trips, completed, active, backlog, invalid, horizon, warmup, warnings):
    rows=[r for r in completed if r['depart']>=warmup]
    times=[r['travel_time'] for r in rows]
    mean=lambda xs: statistics.mean(xs) if xs else None
    return {'mean':mean(times),'median':percentile(times,.5),'p95':percentile(times,.95),'delay':mean([r['delay'] for r in rows]),'car_mean':mean([r['travel_time'] for r in rows if r['kind']=='passenger']),'bus_mean':mean([r['travel_time'] for r in rows if r['kind']=='bus']),'sample_size':len(rows),'requested':len(trips),'completed':len(completed),'active':active,'backlog':backlog,'invalid':invalid,'unfinished':active+backlog,'completion_rate':len(completed)/len(trips),'throughput':len(completed)*3600/horizon,'horizon':horizon,'warnings':warnings}
