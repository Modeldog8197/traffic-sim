import type {Run,Scenario,Network,Comparison} from '../domain';

export type RoadMeasure={entries:number;mean_entry_speed:number|null};
export type RunEvidence={id:string;created:number;scenario:Scenario;configuration_hash:string|null;manifest_hash:string;engine:string;measurement_version:number;network:Network;metrics:Run['metrics'];groups:NonNullable<Run['groups']>;roads:Record<string,RoadMeasure>};
export const limitations=[
  'Generated traffic demand and simulated outcomes are not observed Bangalore traffic or an operational recommendation.',
  'Only passenger cars and buses are represented. Motorcycles, auto-rickshaws, pedestrians and cyclists are not adequately modelled.',
  'Routes are chosen at departure. Closures can change feasible departure routes; within-trip dynamic diversion is not modelled.',
  'Completed-trip averages exclude unfinished trips. Read completion, unfinished trips and full-demand loss together.',
  'Occupancy, inferred signal plans, lane discipline and default road attributes require local review.',
  'One seed pair cannot establish uncertainty. Vehicles in one run are not independent experimental replicates.'
];
export function comparison(a:Pick<Run,'network'|'scenario'|'metrics'|'engine'|'manifest_hash'|'measurement_version'>,b:typeof a):Comparison{
  const checks:[string,unknown,unknown][]=[
    ['network content',a.network.version,b.network.version],['trip manifest',a.manifest_hash,b.manifest_hash],
    ['evaluation horizon',a.metrics.horizon,b.metrics.horizon],['warm-up',a.scenario.warmup,b.scenario.warmup],
    ['measurement version',a.measurement_version??1,b.measurement_version??1],['engine',a.engine,b.engine],
    ['routing policy',a.scenario.routing||'departure_fastest',b.scenario.routing||'departure_fastest'],
    ['occupancy assumptions',[a.scenario.car_occupancy??1.5,a.scenario.bus_occupancy??30],[b.scenario.car_occupancy??1.5,b.scenario.bus_occupancy??30]]
  ];
  const reasons=checks.filter(([,x,y])=>JSON.stringify(x)!==JSON.stringify(y)).map(([name])=>'Mismatched '+name);
  const keys=['mean','delay','p95','completion_rate','throughput','completed','invalid','unfinished','bus_mean','person_loss','full_demand_loss','co2_kg','queue_seconds','od_inequality'];
  const num=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?v:null;
  const rows=keys.map(metric=>{const baseline=num(a.metrics[metric]),candidate=num(b.metrics[metric]);return {metric,baseline,candidate,difference:!reasons.length&&baseline!==null&&candidate!==null?candidate-baseline:null};});
  let interpretation='inconclusive';
  if(!reasons.length){
    const meanA=num(a.metrics.mean),meanB=num(b.metrics.mean);
    if(meanA===null||meanB===null)interpretation='completed-trip mean unavailable; compare completion and full-demand outcomes';
    else if(num(a.metrics.completion_rate)===null||num(b.metrics.completion_rate)===null)interpretation='completion unavailable; overall comparison inconclusive';
    else if(b.metrics.completion_rate!<a.metrics.completion_rate!)interpretation=meanB<meanA?'trade-off':'worse under these conditions';
    else interpretation='single paired run; uncertainty not estimated';
  }
  return {compatible:!reasons.length,reasons,rows,interpretation};
}
export function captureRun(id:string,created:number,run:Run):RunEvidence{
  const crossings=(run as Run&{edge_crossings?:{road_id:string;speed_mps:number}[]}).edge_crossings;
  const roads:Record<string,RoadMeasure>={};
  if(crossings){
    for(const r of run.network.roads)roads[r.id]={entries:0,mean_entry_speed:null};
    for(const e of crossings){const r=roads[e.road_id];if(!r)continue;r.mean_entry_speed=((r.mean_entry_speed??0)*r.entries+e.speed_mps)/(r.entries+1);r.entries++;}
  }
  return structuredClone({id,created,scenario:run.scenario,configuration_hash:run.configuration_hash??null,manifest_hash:run.manifest_hash,engine:run.engine,measurement_version:run.measurement_version??1,network:{...run.network,lanes:undefined},metrics:run.metrics,groups:run.groups??[],roads});
}
export function residentSummary(a:RunEvidence,b:RunEvidence){
  const c=comparison(a,b);
  if(!c.compatible)return 'This comparison cannot support a conclusion: '+c.reasons.join('; ')+'.';
  const fmt=(n:number|null|undefined)=>n==null?'unavailable':n.toFixed(1);
  const change=(key:string)=>c.rows.find(r=>r.metric===key)?.difference??null;
  const groups=b.groups.map(g=>({g,base:a.groups.find(x=>x.group===g.group)})).filter(({g,base})=>g.mean!=null&&base?.mean!=null&&!g.small_sample&&!base.small_sample&&g.requested===base.requested);
  const worse=groups.filter(({g,base})=>g.mean!>base!.mean!);
  const better=groups.filter(({g,base})=>g.mean!<base!.mean!);
  return 'In this simulated '+a.metrics.horizon+'-second period, completion changed from '+fmt(a.metrics.completion_rate==null?null:a.metrics.completion_rate*100)+'% to '+fmt(b.metrics.completion_rate==null?null:b.metrics.completion_rate*100)+'%. Full-demand loss changed by '+fmt(change('full_demand_loss'))+' s/request; a positive change is worse. '+better.length+' comparable recorded class/OD groups had lower completed-trip means and '+worse.length+' had higher means. Groups overlap and are not counts of distinct people; small or changed populations are excluded from this summary. This is one recorded seed pair, with no estimated confidence interval. No field impact or police endorsement is established.';
}
