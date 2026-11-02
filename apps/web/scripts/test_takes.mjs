import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL('../src/studio/takes.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});
const {auditionProject,layerTakes,mergeAssets,setGeneration,useTake}=await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);
const project=()=>({id:'p',assets:[{id:'a',kind:'video'},{id:'b',kind:'video',duration:1,source:{layerId:'star'}},{id:'c',kind:'image',source:{layerId:'sky'}}],
  layers:[{id:'star',kind:'media',assetId:'a',start:2,in:1,out:5,name:'Star',mask:'world',blend:'screen',opacity:.8,transform:{x:.2,scale:.7},keys:[{t:1,opacity:.3}],takes:[]},
    {id:'sky',kind:'media',assetId:'c',start:0,in:0,out:8}],media:{audio:{path:'song.wav'}},words:[{text:'fall'}]});

test('preview changes visible pixels source without mutating saved edit or its take history',()=>{
  const p=project(),before=structuredClone(p),q=auditionProject(p,{layerId:'star',assetId:'b'});
  assert.equal(q.layers[0].assetId,'b');assert.deepEqual(p,before);
  assert.deepEqual({...q.layers[0],assetId:'a'},p.layers[0]);assert.equal(q.layers[1],p.layers[1]);
  assert.equal(q.media,p.media);assert.equal(q.words,p.words);assert.equal(auditionProject(p,null),p);
});
test('accept preserves source trims, keys, placement and original take, including an empty legacy takes array',()=>{
  const p=project(),q=useTake(p,'star','b');
  assert.deepEqual({...q.layers[0],assetId:'a',takes:[]},p.layers[0]);assert.deepEqual(q.layers[0].takes,['a','b']);
  const back=useTake(q,'star','a');assert.equal(back.layers[0].assetId,'a');assert.deepEqual(back.layers[0].takes,['a','b']);
  assert.equal(useTake(p,'star','missing'),p);
});
test('generation drafts survive switching workflows and stay local to each layer',()=>{
  let p=setGeneration(project(),'star','one',{inputs:{prompt:'wind'},sources:{face:'a'},variants:4});
  p=setGeneration(p,'star','two',{inputs:{prompt:'turn'}});p=setGeneration(p,'sky','one',{inputs:{prompt:'clouds'}});p=setGeneration(p,'star','one');
  const saved=JSON.parse(JSON.stringify(p));assert.equal(saved.layers[0].generation.workflowId,'one');
  assert.deepEqual(saved.layers[0].generation.workflows.one,{inputs:{prompt:'wind'},sources:{face:'a'},variants:4});
  assert.equal(saved.layers[1].generation.workflows.one.inputs.prompt,'clouds');
});
test('candidates are isolated by layer; late outputs deduplicate and cannot cross projects',()=>{
  const p=project();assert.deepEqual(layerTakes(p,'star').map(a=>a.id),['a','b']);assert.deepEqual(layerTakes(p,'sky').map(a=>a.id),['c']);
  assert.equal(mergeAssets(p,'other',[{id:'d'}]),p);assert.equal(mergeAssets(p,'p',[p.assets[0]]),p);
  const q=mergeAssets(p,'p',[{id:'d',source:{layerId:'star'}}]);assert.equal(q.layers,p.layers);assert.equal(layerTakes(q,'star').length,3);
});
