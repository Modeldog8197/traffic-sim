import type {Run,Frame,Scenario} from './domain';
import {comparison} from './research/evidence';
import {asset,demoExplanation} from './mode';
type Catalog={defaults:Scenario;demo:any;jobs:any[];tasks:any[];observations:any[];networks:any[]};
let catalogPromise:Promise<Catalog>|undefined;
const networkCache=new Map<string,Promise<Run['network']>>();
async function read<T=any>(path:string,signal?:AbortSignal):Promise<T>{
 const response=await fetch(asset('demo/'+path),{signal});
 if(!response.ok)throw Error('Bundled recording unavailable ('+response.status+'). Reload or use a complete release.');
 return response.json();
}
function catalog(){return catalogPromise??=read<Catalog>('catalog.json').catch(e=>{catalogPromise=undefined;throw e;});}
async function run(id:string,signal?:AbortSignal):Promise<Run>{
 const packed=await read('jobs/'+encodeURIComponent(id)+'/result.json',signal);
 const ref=packed.network_ref;
 if(!networkCache.has(ref))networkCache.set(ref,read('networks/'+encodeURIComponent(ref)+'.json').catch(e=>{networkCache.delete(ref);throw e;}));
 return {...packed,network:await networkCache.get(ref)};
}
export async function demoAPI(path:string,body?:any,method=body===undefined?'GET':'POST',signal?:AbortSignal){
 const url=new URL(path,'https://citylab.invalid'),segments=url.pathname.split('/').filter(Boolean),c=await catalog();
 const local=()=>JSON.parse(localStorage.getItem('citylab.demo.scenarios')||'[]') as (Scenario&{id:string})[];
 if(segments[0]==='scenarios'){
   const scenarios=local();if(method==='GET')return scenarios;
   if(!segments[1])throw Error('A scenario ID is required.');
   const remaining=scenarios.filter(s=>s.id!==segments[1]);
   if(method==='PUT')remaining.push({...body,id:segments[1]});
   else if(method!=='DELETE')throw Error(demoExplanation);
   localStorage.setItem('citylab.demo.scenarios',JSON.stringify(remaining));return {id:segments[1]};
 }
 if(path==='/baseline'){
   if(method==='PUT'){if(!c.jobs.some(j=>j.id===body.id))throw Error('Recorded baseline not found.');localStorage.setItem('citylab.demo.baseline',body.id);}
   return {id:localStorage.getItem('citylab.demo.baseline')||null};
 }
 if(method!=='GET')throw Error(demoExplanation);
 if(path==='/defaults')return c.defaults;
 if(path==='/demo')return {...c.demo,report_url:asset('demo/tasks/'+c.demo.study+'/report.html')};
 if(path==='/networks')return c.networks;
 if(path==='/jobs')return c.jobs;
 if(path==='/tasks')return c.tasks;
 if(path==='/observations')return c.observations;
 if(segments[0]==='network')return read('networks/'+encodeURIComponent(segments[1])+'.json',signal);
 if(segments[0]==='compare'){
   const a=url.searchParams.get('baseline'),b=url.searchParams.get('candidate');if(!a||!b)throw Error('Choose two recorded runs.');
   const [ar,br]=await Promise.all([run(a,signal),run(b,signal)]);return {baseline_id:a,candidate_id:b,...comparison(ar,br)};
 }
 if(segments[0]==='tasks'){
   const task=c.tasks.find(t=>t.id===segments[1]);if(!task)throw Error('Recorded study unavailable.');
   return segments[2]==='result'?read('tasks/'+task.id+'/result.json',signal):task;
 }
 if(segments[0]==='jobs'){
   const job=c.jobs.find(j=>j.id===segments[1]);if(!job)throw Error('Recorded run unavailable.');
   if(!segments[2])return job;
   if(segments[2]==='result')return run(job.id,signal);
   if(segments[2]==='network')return (await run(job.id,signal)).network;
   if(segments[2]==='frames'){
     const index=await read('jobs/'+job.id+'/frames-index.json',signal);
     const offset=Math.max(0,Number(url.searchParams.get('offset')||0)),limit=Math.min(128,Number(url.searchParams.get('limit')||64));
     const frames:Frame[]=[];
     for(let chunk=Math.floor(offset/32);chunk<=Math.floor(Math.min(index.count-1,offset+limit-1)/32);chunk++)frames.push(...await read<Frame[]>('jobs/'+job.id+'/frames/'+String(chunk).padStart(6,'0')+'.json',signal));
     return {frames:frames.slice(offset%32,offset%32+limit),total:index.count,last_time:index.last_time};
   }
 }
 throw Error('This action is not included in the Pages recording. '+demoExplanation);
}
