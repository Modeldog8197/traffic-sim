import {useEffect,useRef,useState,useCallback} from 'react';
import {api} from '../api';
import type {Frame,Job,Scenario} from '../domain';

export function useResource<T>(path:string|null,refresh=0){
 const [state,set]=useState<{key:string|null;data:T|null;error:string;loading:boolean}>({key:null,data:null,error:'',loading:false});
 const version=useRef(0);
 useEffect(()=>{const token=++version.current;const controller=new AbortController();set({key:path,data:null,error:'',loading:!!path});if(path)api<T>(path,undefined,undefined,controller.signal).then(data=>{if(token===version.current)set({key:path,data,error:'',loading:false});}).catch(e=>{if(!controller.signal.aborted&&token===version.current)set({key:path,data:null,error:String(e),loading:false});});return()=>{controller.abort();version.current++;};},[path,refresh]);
 return state.key===path?state:{key:path,data:null,error:'',loading:!!path};
}
export function useJob(id:string|null){
 const [job,set]=useState<Job|null>(null);const [error,setError]=useState('');
 useEffect(()=>{const c=new AbortController();let timer:ReturnType<typeof setTimeout>;set(null);setError('');async function poll(){try{const j=await api<Job>('/jobs/'+id,undefined,undefined,c.signal);if(c.signal.aborted)return;set(j);if(['running','queued','cancelling'].includes(j.status))timer=setTimeout(poll,650);}catch(e){if(!c.signal.aborted)setError(String(e));}}if(id)poll();return()=>{c.abort();clearTimeout(timer);};},[id]);
 return {job:job?.id===id?job:null,error};
}
export function useDraft(initial:Scenario|null){
 const [draft,setDraft]=useState<Scenario|null>(null),[id,setId]=useState<string|null>(null),[past,setPast]=useState<Scenario[]>([]),[future,setFuture]=useState<Scenario[]>([]);
 useEffect(()=>{if(initial)setDraft(d=>d||initial);},[initial]);
 function change(patch:Partial<Scenario>){if(!draft)return;setPast(p=>[...p,draft].slice(-40));setFuture([]);setDraft({...draft,...patch});}
 function load(s:Scenario,key:string|null=null){setDraft(structuredClone(s));setId(key);setPast([]);setFuture([]);}
 function undo(){if(!past.length||!draft)return;setFuture(f=>[draft,...f]);setDraft(past[past.length-1]);setPast(p=>p.slice(0,-1));}
 function redo(){if(!future.length||!draft)return;setPast(p=>[...p,draft]);setDraft(future[0]);setFuture(f=>f.slice(1));}
 return {draft,id,setId,change,load,undo,redo,canUndo:!!past.length,canRedo:!!future.length};
}
// Six 32-frame windows per map. Switching runs destroys the cache and aborts requests.
export function useFrames(id:string|null,time:number,running:boolean){
 const cache=useRef(new Map<number,Frame[]>());const [version,bump]=useState(0);const [total,setTotal]=useState(0);const [error,setError]=useState('');const [lastTime,setLastTime]=useState(0);
 const cacheRun=useRef(id);if(cacheRun.current!==id){cache.current.clear();cacheRun.current=id;}
 const slot=lastTime&&time>=lastTime?Math.max(0,total-1):Math.max(0,Math.floor(time/2)-1);const chunk=Math.floor(slot/32);
 useEffect(()=>{cache.current.clear();setTotal(0);setLastTime(0);setError('');bump(v=>v+1);},[id]);
 useEffect(()=>{if(!id)return;const c=new AbortController();let timer:ReturnType<typeof setTimeout>;async function read(){try{if(!running&&cache.current.has(chunk)&&cache.current.get(chunk)!.length===32)return;const batch=await api<{frames:Frame[];total:number;last_time:number}>(`/jobs/${id}/frames?offset=${chunk*32}&limit=64`,undefined,undefined,c.signal);if(c.signal.aborted)return;cache.current.set(chunk,batch.frames.slice(0,32));if(batch.frames.length>32)cache.current.set(chunk+1,batch.frames.slice(32));while(cache.current.size>6){const farthest=[...cache.current.keys()].sort((a,b)=>Math.abs(b-chunk)-Math.abs(a-chunk))[0];cache.current.delete(farthest);}setTotal(batch.total);setLastTime(batch.last_time||0);bump(v=>v+1);if(running)timer=setTimeout(read,700);}catch(e){if(!c.signal.aborted)setError(String(e));}}read();return()=>{c.abort();clearTimeout(timer);};},[id,chunk,running]);
 void version;
 const frame=time<2?undefined:cache.current.get(chunk)?.[slot%32];
 const next=cache.current.get(Math.floor((slot+1)/32))?.[(slot+1)%32];
 return {frame,next,total,error,cacheSize:cache.current.size};
}
