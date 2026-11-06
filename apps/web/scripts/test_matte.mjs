import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
async function load(path){const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL(path,import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});return import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);}
const m=await load('../src/matte.ts'),{OccupancySource}=await load('../src/placement.ts');
const project=()=>({id:'p',width:200,height:100,duration:5,fps:24,assets:[{id:'a',path:'a.mp4'}],
  analysis:{matte:'analysis/matte/',matteSource:{layerId:'shot',assetId:'a',path:'a.mp4',kind:'video',in:2,out:4,width:100,height:100,fps:24}},
  layers:[{id:'shot',kind:'media',assetId:'a',in:2,out:4,start:1,transform:{x:.1,scale:.5,rotate:90}}]});
test('matte follows layer time and rejects a changed take, missing layer, hidden source or expanded trim',()=>{
  const p=project();assert.equal(m.matteTime(p,.9),undefined);assert.equal(m.matteTime(p,1.5),.5);assert.equal(m.matteTime(p,3),undefined);
  p.layers[0].start=2;assert.equal(m.matteTime(p,2.5),.5);
  p.layers[0].assetId='b';assert.equal(m.matteLayer(p),undefined);p.layers[0].assetId='a';
  p.layers[0].out=4.1;assert.equal(m.matteLayer(p),undefined);p.layers[0].out=4;
  p.layers[0].hidden=true;assert.equal(m.matteTime(p,2.5),undefined);p.layers=[];assert.equal(m.matteLayer(p),undefined);
});
test('matte transform agrees with cover fit, rotation and inverse occupancy sampling',()=>{
  const p=project(),l=p.layers[0],near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
  const center=m.mattePoint(p,l,1,.5,.5);near(center[0],.6);near(center[1],.5);
  const right=m.mattePoint(p,l,1,1,.5);near(right[0],.6);near(right[1],1);
  for(const point of [[0,0],[.2,.9],[1,1]]){const q=m.mattePoint(p,l,1,...point);const r=m.mattePoint(p,l,1,...q,true);near(r[0],point[0]);near(r[1],point[1]);}
});
test('source tracks become composition-time positions and stay absent before/after the layer',()=>{
  const p=project();const raw={fps:24,frames:48,tracks:[{id:'person0',label:'person',frames:Array.from({length:48},(_,f)=>({f,cx:.5,cy:.5,bbox:[.25,.25,.5,.5]}))}]};
  const tr=m.matteTracks(p,raw).tracks[0].frames;assert.equal(tr[0].f,24);assert.equal(tr.at(-1).f,71);assert.equal(tr[0].cx,.6);
  assert.deepEqual(tr[0].bbox,[.475,.25,.25,.5]);assert.equal(raw.tracks[0].frames[0].f,0);
});
test('occupancy samples the transformed matte and does not clamp pixels outside its bounds',()=>{
  const p=project(),l=p.layers[0];l.transform={scale:.25};
  const occ={fps:24,cols:1,rows:1,step:1,frames:[Buffer.from([255]).toString('base64')]};
  const source=new OccupancySource(occ,undefined,24,undefined,false,{frame:f=>{const t=m.matteTime(p,f/24);return t==null?undefined:t*24;},point:(f,x,y)=>m.mattePoint(p,l,f/24,x,y,true)});
  assert.equal(source.at(0),undefined);const g=source.at(24);assert.equal(g.data[0],0);assert.equal(g.data[9*g.cols+16],1);
});
test('prepending time delays original footage matte and tracks, leaving source files unchanged',()=>{
  const p=project();p.analysis={matte:'analysis/matte/'};p.timing={sceneOffset:2};
  const raw={fps:24,frames:48,tracks:[{id:'person0',frames:[{f:0,cx:.5,cy:.5,bbox:[0,0,1,1]}]}]};
  assert.equal(m.matteTime(p,1),undefined);assert.equal(m.matteTime(p,2.5),.5);
  assert.equal(m.matteTracks(p,raw).tracks[0].frames[0].f,48);assert.equal(raw.tracks[0].frames[0].f,0);
});
test('per-clip mattes: the cutout follows the clip on top; a clip without a run cuts nothing out',()=>{
  const p=project();const src=p.analysis.matteSource;
  p.layers=[{id:'shot',kind:'media',assetId:'a',in:2,out:4,start:1},{id:'top',kind:'media',assetId:'a',in:0,out:1,start:2}];
  p.analysis={matte:'analysis/matte_top/',matteSource:{...src,layerId:'top',in:0,out:1},
    mattes:{shot:{matte:'analysis/matte_shot/',matteSource:src},top:{matte:'analysis/matte_top/',matteSource:{...src,layerId:'top',in:0,out:1}}}};
  assert.equal(m.matteEntries(p).map(e=>e.id).sort().join(),'shot,top');
  assert.equal(m.activeMatteAt(p,1.5)?.id,'shot');assert.equal(m.activeMatteAt(p,2.5)?.id,'top');assert.equal(m.activeMatteAt(p,.5),undefined);
  assert.equal(m.matteTime(m.withMatte(p,m.activeMatteAt(p,1.5)),1.5),.5);
  delete p.analysis.mattes.top;p.analysis.matte=null;p.analysis.matteSource=null;
  assert.equal(m.activeMatteAt(p,2.5),undefined,'top clip covers the shot and has no run');
  p.layers[0].assetId='b';assert.equal(m.matteValid(p,m.matteFor(p,'shot')),false);
});
