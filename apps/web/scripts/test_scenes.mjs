import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL('../src/studio/scenes.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});
const s=await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);
const fixture=()=>({id:'p',assets:[{id:'face',kind:'image'},{id:'a',kind:'video'},{id:'b',kind:'video',source:{kind:'workflow',layerId:'shot'}}],layers:[{id:'shot',kind:'media',assetId:'a',start:2,in:1,out:5,generation:{workflowId:'sing',workflows:{sing:{sources:{image:'face'},mediaFiles:{audio:{path:'vocal.wav',duration:4}},postprocess:{timeScale:1.2,trimStart:.4,fps:24}}}}}],board:{cards:[{id:'group',kind:'group',title:'01 / Arrival',x:0,y:0,w:1000,h:500,layerId:'shot'},{id:'ref',kind:'asset',title:'Face',x:20,y:60,w:200,h:200,layerId:'shot',role:'character',assetId:'face'}]}});
test('legacy board scenes retain recipes, source timing and cards without mutating the project',()=>{
 const p=fixture(),before=structuredClone(p),[scene]=s.scenesOf(p);assert.deepEqual(p,before);assert.equal(scene.name,'Arrival');assert.deepEqual(scene.refs,['face']);assert.deepEqual(scene.takes,['a','b']);assert.equal(scene.generation,p.layers[0].generation);
 const q=s.patchScene(p,scene.id,{name:'Platform',x:-200,y:800});assert.deepEqual(q.board.cards,p.board.cards);assert.equal(q.layers,p.layers);assert.equal(s.scenesOf(JSON.parse(JSON.stringify(q)))[0].name,'Platform');
});
test('new scene recipes and late outputs are independent of timeline selection',()=>{
 let p=fixture();const n=s.newScene(p);p=s.setScenes(p,[...s.scenesOf(p),n]);p=s.setSceneGeneration(p,n.id,'motion',{sources:{image:'face'},inputs:{prompt:'Wind'},variants:2});
 p={...p,assets:[...p.assets,{id:'late',kind:'video',source:{kind:'workflow',sceneId:n.id}}]};
 const [old,next]=s.scenesOf(p);assert.ok(!old.takes.includes('late'));assert.deepEqual(next.takes,['late']);assert.equal(next.clips.length,0);assert.equal(next.generation.workflows.motion.inputs.prompt,'Wind');assert.equal(p.layers[0].assetId,'a');
});
test('deleting a scene does not delete media, clips or recreate the grouping on reload',()=>{
 const p=fixture(),q=s.setScenes(p,[]);assert.deepEqual(s.scenesOf(JSON.parse(JSON.stringify(q))),[]);assert.equal(q.layers,p.layers);assert.equal(q.assets,p.assets);assert.deepEqual(q.board.cards,p.board.cards);
});
test('attaching a new clip to a scene retains its other takes and recipe',()=>{
 const p=fixture(),q=s.attachSceneClip(p,'group','new-clip','b'),[scene]=s.scenesOf(q);assert.deepEqual(scene.clips,['shot','new-clip']);assert.deepEqual(scene.takes,['a','b']);assert.deepEqual(scene.generation,p.layers[0].generation);
});
test('splitting a replaced clip inherits one scene even before grouping is resaved',()=>{
 let p=fixture();p=s.setScenes(p,s.scenesOf(p));p={...p,layers:[{...p.layers[0],assetId:'b'},{...p.layers[0],id:'split',assetId:'b',start:4,in:3}]};
 assert.ok(s.scenesOf(p)[0].clips.includes('split'));assert.equal(p.board.scenes[0].clips.includes('split'),false);
});
test('legacy motion cards are reusable takes',()=>{
 const p=fixture();p.board.cards.push({id:'motion-group',kind:'group',title:'Variants',x:1100,y:0,w:1000,h:500},{id:'motion',kind:'asset',assetId:'b',role:'motion',x:1120,y:50,w:200,h:200});
 const scenes=s.scenesOf(p);assert.ok(scenes[1].takes.includes('b'));assert.equal(scenes[1].refs.includes('b'),false);
});
