import type {Dataset} from './observations';
import type {RunEvidence} from './evidence';
import {comparison} from './evidence';

export type Definition={name:string;location:string;network:string;boundary:string[];question:string;intervention:string;primary:string;target:number;sources:string;assumptions:string;limitations:string;notes:string;locked_at:string|null};
export type ResidentNote={id:string;date:string;road_id:string;kind:'queue'|'obstruction'|'congestion';recurrence:string;detail:string;status:'Unverified local observation'};
export type Snapshot={id:string;created_at:string;definition:Definition;baseline:RunEvidence;candidate:RunEvidence;observations:Dataset[];resident_notes:ResidentNote[];protocol:'prospective'|'retrospective';digest:string};
export type Study={schema_version:1;id:string;created_at:string;updated_at:string;definition:Definition;observations:Dataset[];resident_notes:ResidentNote[];evidence:Snapshot[];calibration_links:{dataset:string;backend_id:string;fit_end:number;validation_start:number}[]};
export type StorageLike=Pick<Storage,'getItem'|'setItem'>;
export const studyKey='citylab.research.studies.v1';
export function newStudy(network='synthetic'):Study{
  const now=new Date().toISOString();
  return {schema_version:1,id:crypto.randomUUID(),created_at:now,updated_at:now,definition:{name:'Untitled neighbourhood study',location:'HSR Layout, Bangalore',network,boundary:[],question:'',intervention:'',primary:'full_demand_loss',target:0,sources:'',assumptions:'Generated demand; uncalibrated unless observations demonstrate otherwise.',limitations:'Motorcycles and auto-rickshaws are not represented separately.',notes:'',locked_at:null},observations:[],resident_notes:[],evidence:[],calibration_links:[]};
}
export function validateDefinition(d:Definition){
  for(const key of ['name','location','question','intervention'] as const)if(!d[key].trim()||d[key].length>1000)throw Error('Provide a study '+key+' (up to 1,000 characters).');
  if(!d.boundary.length||d.boundary.length>30||new Set(d.boundary).size!==d.boundary.length)throw Error('Select 1–30 distinct connecting roads for a junction or short corridor.');
  if(!['full_demand_loss','delay','queue_seconds'].includes(d.primary)||!Number.isFinite(d.target)||d.target<0||d.target>100)throw Error('Choose an available primary outcome and a reduction target from 0–100%.');
}
export function readStudies(storage:StorageLike):Study[]{
  const raw=storage.getItem(studyKey);if(!raw)return [];
  let value:unknown;try{value=JSON.parse(raw);}catch{throw Error('Saved studies could not be read. Export/recover browser storage before clearing it.');}
  if(!Array.isArray(value)||value.some(s=>s.schema_version!==1||typeof s.id!=='string'||!s.definition||!Array.isArray(s.evidence)||!Array.isArray(s.observations)))throw Error('Saved studies have an unsupported format.');
  return structuredClone(value);
}
export function saveStudy(storage:StorageLike,study:Study):Study{
  const studies=readStudies(storage),old=studies.find(s=>s.id===study.id);
  if(old)for(const snapshot of old.evidence)if(JSON.stringify(study.evidence.find(s=>s.id===snapshot.id))!==JSON.stringify(snapshot))throw Error('Saved evidence is immutable. Create a new snapshot instead.');
  const saved=structuredClone({...study,updated_at:new Date().toISOString()});
  const rows=studies.filter(s=>s.id!==saved.id);rows.unshift(saved);
  try{storage.setItem(studyKey,JSON.stringify(rows));}catch{throw Error('Browser storage is full or unavailable. Export this study before closing; it has not been saved.');}
  return saved;
}
export function duplicateStudy(study:Study):Study{
  const copy=structuredClone(study),now=new Date().toISOString();
  return {...copy,id:crypto.randomUUID(),created_at:now,updated_at:now,definition:{...copy.definition,name:copy.definition.name+' copy',locked_at:null},evidence:[]};
}
function canonical(value:unknown):string{
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.entries(value).filter(([,v])=>v!==undefined).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+':'+canonical(v)).join(',')+'}';
  return JSON.stringify(value);
}
async function digest(value:unknown){
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value)));
  return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
}
export async function freezeEvidence(study:Study,baseline:RunEvidence,candidate:RunEvidence):Promise<Study>{
  validateDefinition(study.definition);
  if(!study.definition.locked_at)throw Error('Lock the research question and success criteria before attaching evidence.');
  if(baseline.id===candidate.id)throw Error('Choose distinct baseline and intervention runs.');
  const pair=comparison(baseline,candidate);if(!pair.compatible)throw Error(pair.reasons.join('; '));
  if(study.definition.network!==baseline.network.id||study.definition.boundary.some(id=>!baseline.network.roads.some(r=>r.id===id)))throw Error('Study boundary and selected evidence must use the same network.');
  if(study.observations.some(d=>d.network_version!==baseline.network.version))throw Error('Observation network differs from the recorded evidence.');
  const known=new Map(baseline.network.roads.map(r=>[r.id,r]));
  const reached=new Set([study.definition.boundary[0]]);let changed=true;
  while(changed){changed=false;for(const id of study.definition.boundary)if(!reached.has(id)){const r=known.get(id)!;if([...reached].some(k=>{const q=known.get(k)!;return [q.from,q.to].some(n=>n===r.from||n===r.to);})){reached.add(id);changed=true;}}}
  if(reached.size!==study.definition.boundary.length)throw Error('Select one connected junction/corridor, including the connecting roads.');
  const snapshot:Omit<Snapshot,'digest'>={id:crypto.randomUUID(),created_at:new Date().toISOString(),definition:structuredClone(study.definition),baseline:structuredClone(baseline),candidate:structuredClone(candidate),observations:structuredClone(study.observations),resident_notes:structuredClone(study.resident_notes),protocol:Math.min(baseline.created,candidate.created)*1000>Date.parse(study.definition.locked_at)?'prospective':'retrospective'};
  return {...structuredClone(study),evidence:[...study.evidence,{...snapshot,digest:await digest(snapshot)}]};
}
export async function importStudy(text:string):Promise<Study>{
  if(new TextEncoder().encode(text).length>15_000_000)throw Error('Study JSON exceeds 15 MB.');
  const s=JSON.parse(text) as Study;
  if(s.schema_version!==1||!s.definition||!Array.isArray(s.evidence)||!Array.isArray(s.observations)||!Array.isArray(s.resident_notes)||!Array.isArray(s.calibration_links))throw Error('Unsupported study export.');
  if(typeof s.id!=='string'||typeof s.definition.name!=='string'||!Array.isArray(s.definition.boundary))throw Error('Malformed study definition.');
  if(s.definition.locked_at)validateDefinition(s.definition);
  for(const snapshot of s.evidence){
    const {digest:expected,...payload}=snapshot;
    if(expected!==await digest(payload))throw Error('Evidence snapshot integrity check failed.');
    if(!comparison(snapshot.baseline,snapshot.candidate).compatible)throw Error('Imported comparison is incompatible.');
  }
  return structuredClone(s);
}
