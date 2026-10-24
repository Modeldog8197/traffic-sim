import {isDemo,asset} from './mode';
import {demoAPI} from './demo';
export async function api<T=any>(path:string,body?:unknown,method?:string,signal?:AbortSignal,headers:Record<string,string>={}):Promise<T>{
 if(isDemo)return demoAPI(path,body,method,signal) as Promise<T>;
 const response=await fetch('/api'+path,{method:method||(body===undefined?'GET':'POST'),headers:{'Content-Type':body instanceof Blob?body.type||'application/octet-stream':'application/json',...headers},body:body===undefined?undefined:body instanceof Blob?body:JSON.stringify(body),signal});
 const data=await response.json();
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));
 return data;
}
export function download(name:string,data:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function downloadText(name:string,text:string,type='text/plain'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function evidenceURL(path:string){return isDemo?asset('demo/'+path.replace(/^\/api\//,'')):path;}
