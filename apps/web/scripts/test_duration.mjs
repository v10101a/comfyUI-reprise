import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
async function load(path){const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL(path,import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});return import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);}
const {setDuration,setMediaLength,fitLayerEnd,placeTimelineAssets,fitSongRange}=await load('../src/studio/duration.ts');
const {layerSourceTime,dragLayer}=await load('../src/layers.ts');
const {toSong}=await load('../src/audioClip.ts');
const asset={id:'a',kind:'video',path:'a.mp4',duration:6,fps:24};
const project=()=>({fps:24,duration:5,assets:[asset],media:{audioClip:{in:10,out:15,offset:0}},analysis:{},words:[{start:1,end:4}],
  layers:[{id:'l',kind:'media',assetId:'a',start:2,in:1,out:3,keys:[{t:0,x:.2}],transform:{scale:.8},mask:'world',takes:['a']}]});

test('timeline length uses frame boundaries and preserves all source/word/audio edits',()=>{
  const p=project(),q=setDuration(p,10.01);assert.equal(q.duration,10);
  for(const key of ['layers','media','words','assets'])assert.equal(q[key],p[key]);
  assert.equal(setDuration(p,.01).duration,1/24);
  for(const value of [NaN,Infinity,0,-1])assert.equal(setDuration(p,value),p);
  assert.equal(setDuration(p,5),p);
});
test('untrim reaches the source end and grows playback/export to the layer end',()=>{
  const p=project(),q=setMediaLength(p,'l',10);assert.equal(q.layers[0].out,6);assert.equal(q.duration,7);
  assert.deepEqual({...q.layers[0],out:3},p.layers[0]);assert.equal(q.media,p.media);
  const shorter=setMediaLength(q,'l',1);assert.equal(shorter.layers[0].out,2);assert.equal(shorter.duration,7);
});
test('stills extend freely; videos stop when their timeline clip ends',()=>{
  const p=project();p.assets=[{...asset,kind:'image'}];const q=setMediaLength(p,'l',20);assert.equal(q.duration,22);
  assert.deepEqual({...q.layers[0],out:3},p.layers[0]);
  assert.equal(layerSourceTime(p.layers[0],4),undefined);
});
test('dragging to the right includes the full layer; head trim never moves before zero; tail respects fractional source end',()=>{
  const p=project(),l=p.layers[0],moved=dragLayer(l,asset,'move',10,24);assert.equal(fitLayerEnd(p,moved).duration,14);
  const trimmed=dragLayer({...l,start:0},asset,'head',-1,24);assert.equal(trimmed.start,0);assert.equal(trimmed.in,1);
  assert.ok(dragLayer(l,{...asset,duration:5.98},'tail',10,24).out<=5.98);
});
test('dropping footage places full sources consecutively at the cursor and expands the edit',()=>{
  const p=project(),original=structuredClone(p),b={...asset,id:'b',duration:4},still={id:'i',kind:'image'};
  const {project:q,layerId}=placeTimelineAssets(p,[asset,b,still],5);
  assert.deepEqual(q.layers.filter(l=>l.id!=='l').map(l=>[l.start,l.in,l.out]),[[5,0,6],[11,0,4],[15,0,5]]);
  assert.equal(q.duration,20);assert.equal(q.layers.at(-1).id,layerId);assert.equal(q.assets.length,3);
  assert.equal(q.media,p.media);assert.equal(q.words,p.words);assert.deepEqual(p,original);
  const r=placeTimelineAssets(p,[b],1).project;assert.equal(r.duration,5);assert.equal(r.layers.at(-1).start,1);
});
test('a generated take can be added again as independent footage with its recipe and alternatives',()=>{
  const p=project(),candidate={...asset,id:'b',duration:4,source:{kind:'workflow',layerId:'l'}};
  p.assets.push(candidate);p.layers[0].generation={workflowId:'w',workflows:{w:{inputs:{prompt:'turn'}}}};
  const before=structuredClone(p),q=placeTimelineAssets(p,[candidate,candidate],5).project;
  const clips=q.layers.slice(1);assert.deepEqual(clips.map(l=>[l.assetId,l.start,l.in,l.out]),[['b',5,0,4],['b',9,0,4]]);
  assert.notEqual(clips[0].id,clips[1].id);assert.equal(q.duration,13);assert.deepEqual(q.layers[0],before.layers[0]);
  assert.equal(clips[0].mask,undefined);assert.equal(clips[0].keys,undefined);assert.deepEqual(clips[0].takes,['b','a']);
  clips[0].generation.workflows.w.inputs.prompt='another';assert.deepEqual(p,before);
  assert.equal(clips[1].generation.workflows.w.inputs.prompt,'turn');
});
test('revealing earlier song inserts time ahead of all existing content without changing A/V sync',()=>{
  const p=project();p.media.audio={path:'song.wav',duration:30};p.shots=[{id:'shot',start:1,end:2}];p.surfaces=[{keyFrame:24,keys:[{f:48,corners:[]}]}];
  p.lineMeta={one:{generation:{start:1,referenceImage:'ref.png'}}};p.timing={leadMs:40,vocalStart:1};
  p.layers[0].generation={workflows:{w:{mediaFiles:{audio:{path:'drive.wav',duration:5}},postprocess:{trimStart:.2}}}};
  const before=structuredClone(p),{project:q,shift}=fitSongRange(p,{in:8,out:15,offset:-2},30);
  assert.equal(shift,2);assert.equal(q.duration,7);assert.equal(q.timing.sceneOffset,2);assert.equal(q.timing.vocalStart,1);
  assert.equal(q.words[0].start,3);assert.equal(q.words[0].end,6);assert.equal(q.layers[0].start,4);
  assert.equal(q.shots[0].start,3);assert.equal(q.surfaces[0].keyFrame,72);assert.equal(q.surfaces[0].keys[0].f,96);
  assert.equal(q.lineMeta.one.generation.start,3);assert.equal(q.timing.leadMs,40);
  assert.equal(layerSourceTime(q.layers[0],5),layerSourceTime(p.layers[0],3));
  assert.equal(toSong(q,5),toSong(p,3));assert.equal(q.layers[0].keys,p.layers[0].keys);
  assert.deepEqual(q.layers[0].generation,p.layers[0].generation);assert.deepEqual(p,before);
});
test('extending the tail keeps hidden song head and existing content in place; prepends add cumulatively',()=>{
  const p=project();p.shots=[];p.timing={sceneOffset:1};
  const q=fitSongRange(p,{in:10,out:18,offset:-.75},30,false).project;
  assert.equal(q.duration,7.25);assert.equal(q.media.audioClip.offset,-.75);assert.equal(q.words,p.words);assert.equal(q.layers,p.layers);
  const result=fitSongRange(p,{in:9,out:15,offset:-1},30);
  assert.equal(result.project.timing.sceneOffset,2);assert.equal(result.project.duration,6);
});
test('shortening an overshot song refits to the furthest visual or word, never to an unused bin asset',()=>{
  const p=project();p.duration=40;p.shots=[];p.layers[0].start=8;
  p.assets.push({id:'unused',kind:'video',duration:100});
  const q=fitSongRange(p,{in:10,out:12,offset:0},30,false).project;
  assert.equal(q.duration,10);assert.equal(q.words,p.words);assert.equal(q.layers,p.layers);
  const text=fitSongRange({...p,layers:[]},{in:10,out:12,offset:0},30,false).project;
  assert.equal(text.duration,4);
  p.layers[0].out+=.0002;
  assert.equal(fitSongRange(p,{in:10,out:12,offset:0},30,false).project.duration,10+1/24);
});
test('trimming a previously extended head back removes the lead-in and restores content positions',()=>{
  const p=project();p.shots=[];p.media.audio={path:'song.wav',duration:30};
  const grown=fitSongRange(p,{in:8,out:15,offset:-2},30).project;
  const {project:q,shift}=fitSongRange(grown,{in:10,out:15,offset:2},30);
  assert.equal(shift,-2);assert.equal(q.duration,5);assert.equal(q.timing.sceneOffset,0);
  assert.deepEqual(q.words,p.words);assert.deepEqual(q.layers,p.layers);assert.deepEqual(q.media,p.media);
});
