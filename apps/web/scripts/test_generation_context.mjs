import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
async function module(path){const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL(path,import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});return import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);}
const g=await module('../src/studio/generationContext.ts'),s=await module('../src/studio/scenes.ts');
const recipe={inputs:{prompt:'Sing softly',seed:509},sources:{image:'still',audio:'@prepared'},mediaFiles:{audio:{path:'vocal.wav',name:'Phrase vocal',duration:5.28}},postprocess:{fps:24,trimStart:.25,timeScale:.8}};
const fixture=()=>({id:'p',assets:[{id:'take',kind:'video',source:{kind:'workflow',workflowId:'sing',regeneration:structuredClone(recipe),inputs:{image:'/staged/still.png',audio:'/staged/vocal.wav',seed:1},from:{image:{assetId:'still'},audio:{path:'vocal.wav',start:0,end:5.28}}}},{id:'still',kind:'image',source:{kind:'workflow',workflowId:'look',regeneration:{sources:{identity:'face',hair:'hair'}}}},{id:'face',kind:'image'},{id:'hair',kind:'image'},{id:'loose',kind:'image'}],layers:[{id:'clip',kind:'media',assetId:'take',start:1,in:.2,out:3}],board:{cards:[],scenes:[{id:'a',name:'Phrase',x:0,y:0,takes:['take','loose'],refs:['face'],clips:['clip'],generation:{workflowId:'other',workflows:{other:{inputs:{prompt:'Other scene'}}}}},{id:'b',name:'Other',x:400,y:0,takes:[],refs:[],clips:[]}]}});
test('selected take restores its own still, prepared vocal, prompt, seed and timing without staged paths',()=>{
 const p=fixture(),before=structuredClone(p),gen=g.takeGeneration(p,s.sceneForId(p,'a'),'take'),d=gen.workflows.sing;
 assert.equal(gen.workflowId,'sing');assert.deepEqual(d.inputs,recipe.inputs);assert.deepEqual(d.sources,recipe.sources);assert.deepEqual(d.mediaFiles,recipe.mediaFiles);assert.deepEqual(d.postprocess,recipe.postprocess);assert.deepEqual(d.sourceWindows.audio,{start:0,end:5.28});assert.deepEqual(p,before);
});
test('raw provenance keeps exact extraction times and vocal windows',()=>{
 const d=g.assetGeneration({source:{workflowId:'wf',inputs:{image:'staged.png',audio:'staged.wav',prompt:'Turn'},from:{image:{assetId:'video',time:2.75},audio:{audio:'song.wav',start:4,end:7}}}}).workflows.wf;
 assert.deepEqual(d.inputs,{prompt:'Turn'});assert.deepEqual(d.sources,{image:'video',audio:'@song'});assert.deepEqual(d.sourceWindows,{image:{time:2.75},audio:{start:4,end:7}});
 assert.equal(g.assetGeneration({source:{workflowId:'wf'}}),undefined);
});
test('reference lineage preserves identity and hair and stops at cycles or missing assets',()=>{
 const p=fixture();p.assets[2].source={workflowId:'wf',from:{image:{assetId:'take'},missing:{assetId:'gone'}}};
 assert.deepEqual(g.relatedReferences(p,'take'),['still','face','hair']);assert.equal(g.inheritedReference(p,'take','hair'),'hair');assert.equal(g.inheritedReference(p,'take','image'),'still');
});
test('editing a take persists separately from its original provenance, scene recipe and timeline',()=>{
 const p=fixture(),before=structuredClone(p),q=g.setTakeGeneration(p,'a','take','sing',{inputs:{prompt:'Lean in',seed:510}}),saved=JSON.parse(JSON.stringify(q));
 const d=g.takeGeneration(saved,s.sceneForId(saved,'a'),'take').workflows.sing;
 assert.deepEqual(d.sources,recipe.sources);assert.equal(d.inputs.prompt,'Lean in');assert.equal(g.assetGeneration(q.assets[0]).workflows.sing.inputs.prompt,'Sing softly');
 assert.deepEqual(s.sceneForId(q,'a').generation,s.sceneForId(p,'a').generation);assert.equal(q.layers,p.layers);assert.equal(q.assets,p.assets);assert.deepEqual(p,before);
});
test('changing workflow keeps the edited draft when returning',()=>{
 let p=fixture();p=g.setTakeGeneration(p,'a','take','sing',{inputs:{prompt:'Changed'}});p=g.setTakeGeneration(p,'a','take','look',{sources:{identity:'face'}});p=g.setTakeGeneration(p,'a','take','sing');
 const gen=g.takeGeneration(p,s.sceneForId(p,'a'),'take');assert.equal(gen.workflowId,'sing');assert.equal(gen.workflows.sing.inputs.prompt,'Changed');assert.equal(gen.workflows.look.sources.identity,'face');
});
test('moving and combining scenes keep edited take settings attached to the take',()=>{
 const p=g.setTakeGeneration(fixture(),'a','take','sing',{inputs:{prompt:'Changed'}}),q=s.moveSceneTake(p,'take','b');
 assert.equal(s.sceneForId(q,'a').takeGenerations.take,undefined);assert.equal(g.takeGeneration(q,s.sceneForId(q,'b'),'take').workflows.sing.inputs.prompt,'Changed');
 const merged=s.combineScenes(q,'a',['b'],'Combined');assert.equal(g.takeGeneration(merged,s.sceneForId(merged,'a'),'take').workflows.sing.inputs.prompt,'Changed');assert.equal(merged.layers,p.layers);assert.equal(merged.assets,p.assets);
});
