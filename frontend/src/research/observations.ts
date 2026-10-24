import type {Network} from '../domain';

export const columns = ['location_id','road_id','to_road_id','date','start_time','end_time','timezone','utc_offset','metric','value','unit','vehicle_class','direction','method','source','period','synthetic'] as const;
export type Measurement = 'road_entries'|'entry_speed'|'turn_count'|'queue'|'signal_green';
export type Observation = Record<typeof columns[number], string> & {
  metric:Measurement; amount:number; start:number; end:number; synthetic:string;
};
export type Dataset = {id:string; network:string; network_version:string; imported_at:string; rows:Observation[]; original_csv:string};
export const uses:Record<Measurement,string> = {
  road_entries:'Demand calibration or held-out validation: directed-road entries, not occupancy.',
  entry_speed:'Held-out checking of arithmetic mean entry speed; not a fitted objective.',
  turn_count:'Context only: turning-demand calibration is not implemented.',
  queue:'Context only: field queue definitions are not matched to the current detector output.',
  signal_green:'Context only: review signal plans manually; no automatic signal calibration.'
};
export function csvCell(value:unknown){return '"' + String(value??'').replaceAll('"','""') + '"';}
export function toCSV(rows:Record<string,unknown>[], header:readonly string[]=columns){
  return header.join(',')+'\r\n'+rows.map(row=>header.map(k=>csvCell(row[k])).join(',')).join('\r\n')+'\r\n';
}
export function parseCSV(text:string):Record<string,string>[]{
  if(new TextEncoder().encode(text).length>5_000_000)throw Error('CSV exceeds 5 MB.');
  const rows:string[][]=[];let row:string[]=[],cell='',quoted=false,closed=false;
  text=text.replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++){
    const ch=text[i];
    if(quoted){if(ch==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=ch;continue;}
    if(ch==='"'){if(cell||closed)throw Error('Invalid CSV quotation.');quoted=true;continue;}
    if(ch===','||ch==='\n'||ch==='\r'){
      row.push(cell);cell='';closed=false;
      if(ch!==','){if(ch==='\r'&&text[i+1]==='\n')i++;if(row.some(v=>v.trim()))rows.push(row);row=[];}
    }else{if(closed)throw Error('Unexpected text after quoted CSV cell.');cell+=ch;}
  }
  if(quoted)throw Error('Unclosed CSV quotation.');
  if(cell||row.length){row.push(cell);if(row.some(v=>v.trim()))rows.push(row);}
  const header=rows.shift()?.map(s=>s.trim());
  if(!header||new Set(header).size!==header.length||columns.some(c=>!header.includes(c))||header.some(c=>!(columns as readonly string[]).includes(c)))throw Error('Use the supplied field-observation CSV template with all columns.');
  if(!rows.length||rows.length>2000)throw Error('Provide 1–2000 observation rows.');
  return rows.map((r,i)=>{if(r.length!==header.length)throw Error('CSV row '+(i+2)+': wrong number of columns.');return Object.fromEntries(header.map((h,j)=>[h,r[j].trim()]));});
}
function timestamp(date:string,time:string,zone:string,offset:string){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!/^\d{2}:\d{2}:\d{2}$/.test(time)||! /^[+-]\d{2}:\d{2}$/.test(offset))throw Error('Use YYYY-MM-DD, HH:mm:ss and an explicit UTC offset such as +05:30.');
  const stamp=Date.parse(date+'T'+time+offset);
  if(!Number.isFinite(stamp))throw Error('Invalid observation date/time.');
  let parts:Record<string,string>;
  try{parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(stamp).map(p=>[p.type,p.value]));}
  catch{throw Error('Unknown IANA time zone.');}
  if(parts.year+'-'+parts.month+'-'+parts.day!==date||parts.hour+':'+parts.minute+':'+parts.second!==time)throw Error('Date/time and UTC offset do not agree with the selected time zone.');
  return stamp;
}
export function importObservations(text:string,network:Network,mapping:Record<string,string>={}):Dataset{
  const input=parseCSV(text), known=new Map(network.roads.map(r=>[r.id,r]));
  const rows:Observation[]=[];
  for(const [i,raw] of input.entries()){
    try{
      const r={...raw};
      for(const k of ['location_id','date','start_time','end_time','timezone','utc_offset','metric','value','unit','vehicle_class','direction','method','source','period','synthetic'])if(!r[k])throw Error('Missing '+k+'.');
      if(Object.values(r).some(v=>v.length>500))throw Error('A field exceeds 500 characters.');
      r.road_id=r.road_id||mapping[r.location_id]||'';
      if(!known.has(r.road_id))throw Error('Map location "'+r.location_id+'" explicitly to a known directed road.');
      if(!(r.metric in uses))throw Error('Unknown measurement type.');
      if(!['calibration','validation','context'].includes(r.period))throw Error('Period must be calibration, validation or context.');
      if(!['true','false'].includes(r.synthetic))throw Error('Synthetic must explicitly be true or false.');
      if(!['all','passenger','bus','motorcycle','auto_rickshaw'].includes(r.vehicle_class))throw Error('Unknown vehicle class.');
      const amount=Number(r.value);
      const spec:Record<string,[string,number,boolean]>={road_entries:['vehicles',100000,true],entry_speed:['m/s',70,false],turn_count:['vehicles',100000,true],queue:['vehicles',10000,true],signal_green:['s',180,false]};
      const [unit,max,integer]=spec[r.metric];
      if(!Number.isFinite(amount)||amount<0||amount>max||(integer&&!Number.isInteger(amount))||r.unit!==unit)throw Error('Invalid value or unit for '+r.metric+'. Expected '+unit+'.');
      if(['turn_count','queue','signal_green'].includes(r.metric)&&r.period!=='context')throw Error(r.metric+' is contextual only; it is not calibrated or validated by the current model.');
      if(r.metric==='entry_speed'&&r.period==='calibration')throw Error('Entry speed can check performance but is not a demand-fitting objective.');
      if(['motorcycle','auto_rickshaw'].includes(r.vehicle_class)&&r.period!=='context')throw Error('Motorcycles and auto-rickshaws are not represented separately; keep their measurements as context.');
      if(r.metric==='turn_count'){
        if(!known.has(r.to_road_id)||known.get(r.road_id)!.to!==known.get(r.to_road_id)!.from)throw Error('Turning observation needs a connected outgoing road; supported turns still require field review.');
      }else if(r.to_road_id)throw Error('to_road_id is only used for turning counts.');
      const start=timestamp(r.date,r.start_time,r.timezone,r.utc_offset),end=timestamp(r.date,r.end_time,r.timezone,r.utc_offset);
      if(end<=start)throw Error('End must be later than start on the same date. Split overnight intervals.');
      if(rows.some(q=>q.road_id===r.road_id&&q.to_road_id===r.to_road_id&&q.metric===r.metric&&(q.vehicle_class===r.vehicle_class||[q.vehicle_class,r.vehicle_class].includes('all'))&&Math.max(start,q.start)<Math.min(end,q.end)))throw Error('Duplicate or overlapping intervals/classes, including across calibration and validation.');
      rows.push({...r,metric:r.metric as Measurement,amount,start,end} as Observation);
    }catch(error){throw Error('CSV row '+(i+2)+': '+(error as Error).message);}
  }
  for(const row of rows.filter(r=>r.metric==='entry_speed')){
    const count=rows.find(c=>c.metric==='road_entries'&&c.road_id===row.road_id&&c.start===row.start&&c.end===row.end&&c.vehicle_class===row.vehicle_class);
    if(!count||count.amount===0||count.period!==row.period)throw Error('Entry speed requires a matching positive road-entry count in the same interval/class and period.');
  }
  return {id:crypto.randomUUID(),network:network.id,network_version:network.version,imported_at:new Date().toISOString(),rows,original_csv:text};
}
export function calibrationCSV(dataset:Dataset){
  const counts=dataset.rows.filter(r=>r.metric==='road_entries'&&r.period!=='context');
  const fit=counts.filter(r=>r.period==='calibration'),validation=counts.filter(r=>r.period==='validation');
  if(!fit.length||!validation.length)throw Error('Provide both calibration and untouched validation road-entry intervals.');
  if(new Set(counts.map(r=>r.synthetic)).size>1)throw Error('Do not mix field and synthetic observations in one calibration.');
  if(new Set(counts.map(r=>r.date+'|'+r.timezone+'|'+r.utc_offset)).size!==1)throw Error('Select one observation date, time zone and offset per calibration; never pool days silently.');
  const origin=Math.min(...counts.map(r=>r.start));
  const fitEnd=(Math.max(...fit.map(r=>r.end))-origin)/1000;
  const validationStart=(Math.min(...validation.map(r=>r.start))-origin)/1000;
  const end=(Math.max(...counts.map(r=>r.end))-origin)/1000;
  if(fitEnd>validationStart)throw Error('Calibration must finish before validation begins across all roads.');
  if(end>5400)throw Error('Calibration window exceeds the model’s 5,400-second maximum horizon.');
  const rows=counts.map(r=>({road_id:r.road_id,start_s:(r.start-origin)/1000,end_s:(r.end-origin)/1000,vehicle_count:r.amount,vehicle_class:r.vehicle_class,mean_speed_mps:dataset.rows.find(s=>s.metric==='entry_speed'&&s.road_id===r.road_id&&s.start===r.start&&s.end===r.end&&s.vehicle_class===r.vehicle_class)?.amount??''}));
  return {csv:toCSV(rows,['road_id','start_s','end_s','vehicle_count','mean_speed_mps','vehicle_class']),fitEnd,validationStart,horizon:end,provenance:(counts[0].synthetic==='true'?'Synthetic example; not field validation. ':'Field observations supplied by user; not independently verified. ')+counts[0].date+' '+counts[0].timezone+'; dataset '+dataset.id};
}
export function syntheticExample(rows:{road_id:string;start_s:number;end_s:number;vehicle_count:number}[]){
  const time=(s:number)=>new Date(Date.UTC(2000,0,1,8,0,s)).toISOString().slice(11,19);
  return toCSV(rows.map(r=>({location_id:r.road_id,road_id:r.road_id,to_road_id:'',date:'2000-01-01',start_time:time(r.start_s),end_time:time(r.end_s),timezone:'Asia/Kolkata',utc_offset:'+05:30',metric:'road_entries',value:r.vehicle_count,unit:'vehicles',vehicle_class:'all',direction:'Directed road '+r.road_id,method:'SUMO edge-entry recording',source:'Bundled seed 9; synthetic date placeholder, not a field collection date',period:r.end_s<=60?'calibration':'validation',synthetic:'true'})));
}
