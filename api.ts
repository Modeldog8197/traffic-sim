export async function api<T=any>(path:string,body?:unknown,method?:string,signal?:AbortSignal):Promise<T>{
 const response=await fetch('/api'+path,{method:method||(body===undefined?'GET':'POST'),headers:body instanceof Blob?{'Content-Type':body.type||'application/octet-stream'}:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof Blob?body:JSON.stringify(body),signal});
 const data=await response.json();
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));
 return data;
}
export function download(name:string,data:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
