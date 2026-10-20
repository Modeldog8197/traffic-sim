import type {Frame,Network,Vehicle} from './domain';
function pointAt(coords:number[][],distance:number,length:number){if(coords.length<2)return coords[0];const spans=coords.slice(1).map((p,i)=>Math.hypot(p[0]-coords[i][0],p[1]-coords[i][1]));const target=spans.reduce((a,b)=>a+b,0)*Math.max(0,Math.min(1,distance/length));let d=0;for(let i=0;i<spans.length;i++){if(d+spans[i]>=target){const f=spans[i]?(target-d)/spans[i]:0;return [coords[i][0]+f*(coords[i+1][0]-coords[i][0]),coords[i][1]+f*(coords[i+1][1]-coords[i][1])];}d+=spans[i];}return coords[coords.length-1];}
export function interpolate(a:Frame|undefined,b:Frame|undefined,time:number,network:Network):Vehicle[]{
 if(!a)return [];if(!b||time<=a.time||!network.lanes)return a.vehicles;
 const f=Math.min(1,(time-a.time)/(b.time-a.time));const next=new Map(b.vehicles.map(v=>[v.id,v]));const lanes=network.lanes;
 return a.vehicles.map(v=>{const w=next.get(v.id);if(!w||!lanes[v.lane]||!lanes[w.lane])return v;
 let path=[v.lane];if(v.lane!==w.lane){const queue=[[v.lane]];let found:string[]|undefined;const seen=new Set([v.lane]);while(queue.length){const p=queue.shift()!;if(p.length>7)continue;for(const lane of lanes[p[p.length-1]]?.next||[]){if(lane===w.lane){found=[...p,lane];break;}if(!seen.has(lane)){seen.add(lane);queue.push([...p,lane]);}}if(found)break;}if(!found)return v;path=found;}
 if(path.length===1){if(w.lane_position<v.lane_position)return v;return {...v,position:pointAt(lanes[v.lane].coordinates,v.lane_position+f*(w.lane_position-v.lane_position),lanes[v.lane].length)};}
 const distances=path.map((lane,i)=>i===0?lanes[lane].length-v.lane_position:i===path.length-1?w.lane_position:lanes[lane].length);let remaining=f*distances.reduce((x,y)=>x+y,0);for(let i=0;i<path.length;i++){if(remaining<=distances[i]){const lane=lanes[path[i]];return {...v,position:pointAt(lane.coordinates,remaining+(i===0?v.lane_position:0),lane.length)};}remaining-=distances[i];}return w;});
}
