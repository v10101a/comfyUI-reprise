import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
async function load(path){const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL(path,import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});return import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);}
const {headSourceAt,sampleHead,headPoint,headSpotPoint}=await load('../src/heads.ts');
const {relativeHeadSpot,hudPointer,setHudPointer}=await load('../src/hud.ts');
const {setTextRole}=await load('../src/studio/groups.ts');
const {lineLookOf}=await load('../src/looks.ts');
const p=()=>({width:200,height:100,fps:24,duration:8,media:{video:{path:'original.mp4',duration:5}},analysis:{},shots:[],
  assets:[{id:'a',path:'a.mp4',kind:'video',width:100,height:100},{id:'b',path:'b.mp4',kind:'video',width:200,height:100}],
  layers:[{id:'plate',kind:'plate'},{id:'a',kind:'media',assetId:'a',start:1,in:2,out:4},{id:'b',kind:'media',assetId:'b',start:2,in:0,out:2}]});
test('heads follow the visible shot and source trim; hidden and moved clips reveal the correct source',()=>{
  const q=p();assert.equal(headSourceAt(q,.5).path,'original.mp4');assert.equal(headSourceAt(q,1.5).time,2.5);
  assert.equal(headSourceAt(q,2.5).path,'b.mp4');q.layers[2].hidden=true;assert.equal(headSourceAt(q,2.5).path,'a.mp4');
  q.layers[1].start=3;assert.equal(headSourceAt(q,3.5).time,2.5);assert.equal(headSourceAt(q,7),undefined);
  q.timing={sceneOffset:2};q.layers=q.layers.slice(0,1);assert.equal(headSourceAt(q,1),undefined);assert.equal(headSourceAt(q,2.5).time,.5);
});
test('head coordinates match cover fit, rotation, animated transforms and clip offsets',()=>{
  const q=p();q.layers[1].transform={x:.1,scale:.5,rotate:90};const source=headSourceAt(q,1.5);
  const pt=headPoint(q,source,1.5,{f:1,cx:1,cy:.5,bbox:[.25,.25,.5,.5]});assert.equal(pt.cx,.6);assert.equal(pt.cy,1);assert.deepEqual(pt.bbox,[.475,.25,.25,.5]);
  q.layers[1].keys=[{t:0,x:0},{t:1,x:.2}];assert.equal(headPoint(q,headSourceAt(q,1.5),1.5,{f:1,cx:.5,cy:.5,bbox:[0,0,1,1]}).cx,.6);
});
test('head samples interpolate at the source fps without holding through missing people or beyond the clip',()=>{
  const raw={fps:12,frames:40,tracks:[{id:'person0',frames:[0,1,20].map(f=>({f,cx:f/20,cy:.3,bbox:[0,0,1,1]}))}]};
  assert.equal(sampleHead(raw,1/24).cx,.025);assert.equal(sampleHead(raw,.8),undefined);assert.equal(sampleHead(raw,3),undefined);
  assert.equal(sampleHead(raw,0,'someoneElse'),undefined);assert.equal(sampleHead(undefined,0),undefined);
});
test('shared role changes override HUD layout and retain unselected clip appearance/timing',()=>{
  const q={...p(),look:{id:'hud'},style:{fontSize:.08},words:['a','b','c'].map((id,i)=>({id,lineId:id,text:id,start:i,end:i+1,placement:'overlay',preset:'none'}))};
  const caption=setTextRole(q,['a','b'],'overlay');assert.equal(lineLookOf(caption,'a').layout,'line');assert.equal(lineLookOf(caption,'c').layout,'hud');
  const hud=setTextRole(caption,['a','b'],'anchor');assert.ok(hud.words.slice(0,2).every(w=>w.anchor.trackId==='person0'&&w.preset==='hud'));
  assert.deepEqual(hud.words[2],q.words[2]);assert.deepEqual(hud.words.map(w=>[w.start,w.end]),q.words.map(w=>[w.start,w.end]));
});
test('a chosen spot follows a moving, growing head and round trips through a rotated clip transform',()=>{
  const q=p(),spot={u:.8,v:.2};q.layers[1].transform={x:.1,y:-.05,scale:.7,rotate:35};
  const source=headSourceAt(q,1.5),raw={f:0,cx:.5,cy:.4,bbox:[.25,.2,.4,.5]};
  const map=s=>{const pt=headPoint(q,source,1.5,headSpotPoint(raw,s));return [pt.cx,pt.cy];};
  assert.deepEqual(relativeHeadSpot(map(spot),map({u:0,v:0}),map({u:1,v:0}),map({u:0,v:1})),spot);
  const later=headSpotPoint({...raw,bbox:[.4,.3,.6,.7]},spot);assert.ok(Math.abs(later.cx-.88)<1e-10);assert.ok(Math.abs(later.cy-.44)<1e-10);
  assert.equal(relativeHeadSpot([.5,.5],[0,0],[0,0],[0,0]),undefined);
});
test('pointer visibility and colors are independent, scoped to selected clips, and persist with the attachment',()=>{
  const q={...p(),words:[],look:{id:'hud'},lineMeta:{a:{fill:'#ffffff'},b:{hud:{point:{u:.7,v:.3}}}}};
  const changed=setHudPointer(q,['a','b'],{dot:false,dotColor:'#0000ff80',connectorColor:'#ff0000'});
  const saved=JSON.parse(JSON.stringify(changed));assert.equal(hudPointer(saved,'a').dot,false);assert.equal(hudPointer(saved,'a').connector,true);
  assert.equal(hudPointer(saved,'a').dotColor,'#0000ff80');assert.equal(hudPointer(saved,'a').connectorColor,'#ff0000');
  assert.deepEqual(hudPointer(saved,'b').point,{u:.7,v:.3});assert.equal(hudPointer(saved,'c').dot,true);
  const reset=setHudPointer(saved,['a'],{dotColor:null});assert.equal(hudPointer(reset,'a').connectorColor,'#ff0000');assert.equal(reset.lineMeta.a.fill,'#ffffff');
  assert.deepEqual(q.lineMeta.a,{fill:'#ffffff'});
});
