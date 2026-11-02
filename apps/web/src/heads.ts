import type {Project,Tracks,MediaLayer,Point,HeadSpot} from './types';
import {layersOf,assetOf,layerSourceTime,layerStateAt} from './layers';
type TrackPoint=Tracks['tracks'][number]['frames'][number];
/** Keep a chosen spot proportional to the source head as it moves and changes size. */
export function headSpotPoint(pt:TrackPoint,spot?:HeadSpot):TrackPoint{
  if(!spot)return pt;const [x,y,w,h]=pt.bbox;return {...pt,cx:x+w*spot.u,cy:y+h*spot.v};
}

export type HeadSource={path:string;time:number;width:number;height:number;layer?:MediaLayer};
/** Select the visible shot first, so an untracked foreground clip cannot borrow another shot's person. */
export function headSourceAt(p:Project,t:number):HeadSource|undefined{
  const layers=layersOf(p);
  for(const l of [...layers].reverse()){
    if(l.kind!=='media'||l.hidden||layerStateAt(l,t).opacity<=0)continue;
    const at=layerSourceTime(l,t),a=assetOf(p,l.assetId);if(at==null||!a)continue;
    return {path:a.path,time:a.kind==='image'?0:at,width:a.width||p.width,height:a.height||p.height,layer:l};
  }
  if(!layers.some(l=>l.kind==='plate'&&!l.hidden))return;
  const shot=p.shots.find(s=>s.status==='done'&&s.video&&t>=s.start&&t<s.end);
  if(shot)return {path:shot.video!,time:t-shot.start,width:p.width,height:p.height};
  const at=t-(p.timing?.sceneOffset||0),v=p.media.video;
  if(v&&at>=0&&at<v.duration)return {path:v.path,time:at,width:v.width||p.width,height:v.height||p.height};
}
export function headSourcePaths(p:Project):string[]{
  const paths=p.layers?.flatMap(l=>{const a=l.kind==='media'&&!l.hidden?assetOf(p,l.assetId):undefined;return a?[a.path]:[];})||[];
  if(p.media.video)paths.push(p.media.video.path);
  paths.push(...p.shots.filter(s=>s.status==='done'&&s.video).map(s=>s.video!));return [...new Set(paths)];
}
/** Interpolate adjacent samples; bridge only brief detection gaps, never hold another shot indefinitely. */
export function sampleHead(raw:Tracks|undefined,t:number,id='person0'):TrackPoint|undefined{
  const points=raw?.tracks.find(tr=>tr.id===id)?.frames;if(!points?.length||!raw)return;
  const f=t*raw.fps;let lo=0,hi=points.length-1,at=-1;
  while(lo<=hi){const m=(lo+hi)>>1;if(points[m].f<=f){at=m;lo=m+1;}else hi=m-1;}
  const a=points[at],b=points[at+1];
  if(a&&b&&b.f-a.f<=raw.fps*.26){const k=(f-a.f)/(b.f-a.f);return {...a,f,cx:a.cx+(b.cx-a.cx)*k,cy:a.cy+(b.cy-a.cy)*k,bbox:a.bbox.map((v,i)=>v+(b.bbox[i]-v)*k)};}
  const near=!a?b:!b?a:f-a.f<=b.f-f?a:b;return near&&Math.abs(near.f-f)<=raw.fps*.13?near:undefined;
}
/** Same cover fit, centre rotation, scale and animation as the media layer. */
export function headPoint(p:Project,source:HeadSource,t:number,pt:TrackPoint):TrackPoint{
  const l=source.layer;if(!l)return pt;
  const tr=layerStateAt(l,t).transform,s=Math.max(p.width/source.width,p.height/source.height)*(tr.scale??1),a=(tr.rotate||0)*Math.PI/180;
  const map=(x:number,y:number):Point=>{const dx=(x-.5)*source.width*s,dy=(y-.5)*source.height*s;return [.5+(tr.x||0)+(dx*Math.cos(a)-dy*Math.sin(a))/p.width,.5+(tr.y||0)+(dx*Math.sin(a)+dy*Math.cos(a))/p.height];};
  const [cx,cy]=map(pt.cx,pt.cy),[x,y,w,h]=pt.bbox,corners=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]].map(([x,y])=>map(x,y));
  const xs=corners.map(p=>p[0]),ys=corners.map(p=>p[1]);return {...pt,cx,cy,bbox:[Math.min(...xs),Math.min(...ys),Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)]};
}
