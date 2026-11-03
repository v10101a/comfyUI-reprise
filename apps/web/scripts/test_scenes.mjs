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

const grouped=()=>{
 let p=fixture();p=s.setScenes(p,s.scenesOf(p));
 p.assets.push({id:'c',kind:'video',source:{kind:'workflow',sceneId:'singing',layerId:'second'}},{id:'setting',kind:'image'});
 p.layers.push({id:'second',kind:'media',assetId:'c',start:7,in:.5,out:3.5,transform:{x:.2},keys:[{t:0,scale:1.1}]});
 p.board.scenes.push({id:'singing',name:'Singing alt',x:600,y:900,clips:['second'],takes:['c','b'],refs:['face','setting'],roles:{face:'reference',setting:'setting'},notes:'Held myself',
  generation:{workflowId:'sing',workflows:{sing:{inputs:{prompt:'Another singing take'},sources:{image:'face',audio:'@prepared'},mediaFiles:{audio:{path:'held-word.wav',duration:5}},postprocess:{timeScale:1.6,trimStart:.3,fps:24}}}}});
 p.board.scenes.push({id:'empty',name:'Later',x:-400,y:300,clips:[],takes:[],refs:[]});return p;
};
test('combining imported scenes deduplicates takes and refs while preserving the authored edit and all recipes',()=>{
 const p=grouped(),before=structuredClone(p),q=s.combineScenes(p,'group',['group','singing'],'Maybe I laugh at myself'),scenes=s.scenesOf(q),merged=scenes[0];
 assert.deepEqual(p,before);assert.equal(q.layers,p.layers);assert.equal(q.assets,p.assets);assert.equal(q.board.cards,p.board.cards);
 assert.equal(scenes.length,2);assert.equal(merged.name,'Maybe I laugh at myself');assert.deepEqual(merged.clips,['shot','second']);assert.deepEqual(merged.takes,['a','b','c']);
 assert.deepEqual(merged.refs,['face','setting']);assert.equal(merged.roles.face,'character');assert.match(merged.notes,/Singing alt\nHeld myself/);
 assert.equal(merged.generation,p.board.scenes[0].generation);assert.deepEqual(merged.recipes.map(r=>r.generation),p.board.scenes.slice(0,2).map(x=>x.generation));
 assert.deepEqual(s.scenesOf(JSON.parse(JSON.stringify(q))),scenes);
});
test('switching merged recipes preserves edited prompts, prepared phrase audio and postprocessing independently',()=>{
 let p=s.combineScenes(grouped(),'group',['singing'],'Phrase');
 p=s.selectSceneRecipe(p,'group','singing');p=s.setSceneGeneration(p,'group','sing',{inputs:{prompt:'A quieter laugh'}});
 p=s.selectSceneRecipe(p,'group','group');assert.equal(s.sceneForId(p,'group').generation.workflows.sing.mediaFiles.audio.path,'vocal.wav');
 p=s.selectSceneRecipe(JSON.parse(JSON.stringify(p)),'group','singing');const draft=s.sceneForId(p,'group').generation.workflows.sing;
 assert.equal(draft.inputs.prompt,'A quieter laugh');assert.equal(draft.mediaFiles.audio.path,'held-word.wav');assert.deepEqual(draft.postprocess,{timeScale:1.6,trimStart:.3,fps:24});
});
test('a reference upload started before a merge updates its own recipe, not the selected recipe',()=>{
 const p=s.combineScenes(grouped(),'group',['singing'],'Phrase'),q=s.setSceneGeneration(p,'singing','sing',{sources:{image:'setting'}});
 assert.equal(s.sceneForId(q,'group').generation.workflows.sing.sources.image,'face');
 const chosen=s.selectSceneRecipe(q,'group','singing');assert.equal(s.sceneForId(chosen,'group').generation.workflows.sing.sources.image,'setting');
});
test('late results follow merged IDs through repeated merges and inherit only the combined scene',()=>{
 let p=s.combineScenes(grouped(),'group',['singing'],'Phrase');p=s.combineScenes(p,'empty',['group'],'Song');
 p=JSON.parse(JSON.stringify(p));p.assets.push({id:'late',kind:'video',source:{kind:'workflow',sceneId:'singing',layerId:'second'}});
 p.layers.push({id:'split',kind:'media',assetId:'late',start:10,in:0,out:2});
 const scenes=s.scenesOf(p);assert.equal(scenes.length,1);assert.ok(scenes[0].takes.includes('late'));assert.ok(scenes[0].clips.includes('split'));
 assert.equal(s.sceneForId(p,'singing').id,'empty');assert.equal(s.sceneForId(p,'group').id,'empty');
 const q=s.attachSceneClip(p,'singing','added','late');assert.ok(s.sceneForId(q,'empty').clips.includes('added'));assert.equal(p.layers,q.layers);
});
test('moving a take overrides both clip alternatives and generation provenance after save/reload',()=>{
 const p=grouped();p.layers[0].takes=['a','b'];p.assets[2].source.sceneId='group';const before=structuredClone(p);
 let q=s.moveSceneTake(p,'b','empty');q=JSON.parse(JSON.stringify(q));
 for(let i=0;i<3;i++){const scenes=s.scenesOf(q);assert.deepEqual(scenes.filter(x=>x.takes.includes('b')).map(x=>x.id),['empty']);q=s.setScenes(q,scenes);}
 assert.deepEqual(p,before);assert.deepEqual(q.assets,p.assets);assert.deepEqual(q.layers,p.layers);
 q.assets.push({id:'late',kind:'video',source:{kind:'workflow',sceneId:'group',layerId:'shot'}});
 assert.ok(s.sceneForId(q,'group').takes.includes('late'));assert.ok(!s.sceneForId(q,'empty').takes.includes('late'));
});
test('moving a used take relocates its scene associations without modifying clips or shared references',()=>{
 const p=grouped(),q=s.moveSceneTake(p,'c','group');
 assert.equal(q.layers,p.layers);assert.equal(q.assets,p.assets);assert.deepEqual(s.sceneForId(q,'group').clips,['shot','second']);assert.deepEqual(s.sceneForId(q,'singing').clips,[]);
 assert.deepEqual(s.sceneForId(q,'singing').refs,['face','setting']);assert.ok(!s.sceneForId(q,'singing').takes.includes('c'));
 const merged=s.combineScenes(q,'empty',['group'],'Final');assert.equal(merged.board.takeAssignments.c,'empty');assert.deepEqual(s.scenesOf(merged).filter(x=>x.takes.includes('c')).map(x=>x.id),['empty']);
});
test('scene provenance wins over a different scene using the same generation target clip',()=>{
 const p=grouped();p.assets.push({id:'fresh',kind:'video',source:{kind:'workflow',sceneId:'empty',layerId:'shot'}});
 assert.deepEqual(s.scenesOf(p).filter(x=>x.takes.includes('fresh')).map(x=>x.id),['empty']);
});
test('list edge drops reorder frames while collapsed cards preserve their saved positions',()=>{
 const p=grouped(),ordered=s.placeSceneInList(p,'empty','singing',false);assert.deepEqual(s.scenesOf(ordered).map(x=>x.id),['group','empty','singing']);
 const q=s.patchScene(ordered,'singing',{collapsed:true}),scene=s.sceneForId(JSON.parse(JSON.stringify(q)),'singing');
 assert.equal(scene.x,600);assert.equal(scene.y,900);assert.equal(s.sceneHeight(scene),64);assert.equal(q.layers,p.layers);assert.equal(q.assets,p.assets);
 assert.deepEqual(s.scenesOf(s.placeSceneInList(q,'group','singing',true)).map(x=>x.id),['empty','singing','group']);
});
test('new empty scenes combine without a timeline and invalid organization requests are no-ops',()=>{
 const p={id:'p',assets:[],layers:[],board:{cards:[],scenes:[{id:'a',name:'Idea',x:0,y:0,takes:[],refs:[],clips:[]},{id:'b',name:'Alternative',x:310,y:0,takes:[],refs:[],clips:[]}]}};
 const q=s.combineScenes(p,'a',['b'],'One idea');assert.equal(s.scenesOf(q).length,1);assert.equal(q.layers,p.layers);
 assert.equal(s.combineScenes(p,'missing',['a'],'x'),p);assert.equal(s.combineScenes(p,'a',['missing'],'x'),p);
 assert.equal(s.moveSceneTake(p,'missing','a'),p);assert.equal(s.placeSceneInList(p,'a','a',false),p);assert.equal(s.selectSceneRecipe(p,'a','missing'),p);
});
test('deleting a take only removes the board item and does not return through legacy clip history',()=>{
 const p=grouped();p.layers[0].takes=['a','b'];const q=s.removeSceneTake(p,'group','b');
 assert.equal(q.layers,p.layers);assert.equal(q.assets,p.assets);assert.ok(!s.sceneForId(JSON.parse(JSON.stringify(q)),'group').takes.includes('b'));
 assert.ok(s.sceneForId(q,'singing').takes.includes('b'),'other explicit use remains');
 assert.ok(s.sceneForId(s.moveSceneTake(q,'b','group'),'group').takes.includes('b'),'dragging back restores membership');
 const merged=s.combineScenes(q,'group',['singing'],'Phrase');assert.ok(s.sceneForId(merged,'group').takes.includes('b'),'visible take from merged scene is kept');
});
