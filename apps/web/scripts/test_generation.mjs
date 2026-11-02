import test from 'node:test';
import assert from 'node:assert/strict';
import {generationPlan,setDirection,directionFor} from '../src/studio/generation.ts';

const project=()=>({id:'test',fps:24,duration:12,media:{video:{path:'media/video.mp4'}},shots:[],words:[
  {id:'b',lineId:'one',text:'again!',start:3,end:4},
  {id:'a',lineId:'one',text:'Stay',start:1,end:2},
  {id:'c',lineId:'two',text:'Tonight',start:10.5,end:11.5},
],lineMeta:{one:{scale:1.4},two:{boxes:false}}});

test('whole-line direction preserves exact lyric order, with high detail and quiet motion by default',()=>{
  const p=project(),plan=generationPlan(p,p.words[0]);
  assert.equal(plan.reason,'');assert.deepEqual(plan.body.wordIds,['a','b']);
  assert.equal(plan.body.text,'Stay again!');assert.equal(plan.start,1);assert.equal(plan.end,4);
  assert.equal(plan.body.longEdge,1344);assert.match(plan.body.motionPrompt,/lips gently closed/);
  assert.match(plan.body.motionPrompt,/static shot/);assert.ok(!plan.body.prompt.includes('static shot'));
});
test('direction survives JSON round-trip, stays with its line, and preserves other line settings',()=>{
  const p=project(),q=setDirection(p,'one',{lettering:'Copper on concrete',camera:'push',motion:'Hair moves in the wind.',seed:0});
  const saved=JSON.parse(JSON.stringify(q)),plan=generationPlan(saved,saved.words[0]);
  assert.equal(plan.body.seed,0);assert.equal(plan.body.prompt,'Copper on concrete');assert.match(plan.body.motionPrompt,/pushes in slowly/);
  assert.deepEqual(saved.lineMeta.two,{boxes:false});assert.equal(saved.lineMeta.one.scale,1.4);
  assert.equal(directionFor(p,'one').lettering,undefined);assert.equal(directionFor(saved,'two').lettering,undefined);
});
test('word scope, explicit timing and identity reference are sent independently',()=>{
  let p=project();p=setDirection(p,'one',{scope:'word',start:2,duration:5,referenceImage:'media/face.png',longEdge:736});
  const plan=generationPlan(p,p.words[0]);
  assert.deepEqual(plan.body.wordIds,['b']);assert.equal(plan.body.text,'again!');
  assert.equal(plan.start,2);assert.equal(plan.end,7);assert.equal(plan.body.referenceImage,'media/face.png');
  assert.equal(plan.body.guideFirstFrame,true);assert.equal(plan.body.longEdge,736);
  p=setDirection(p,'one',{referenceImage:undefined});assert.equal(generationPlan(p,p.words[0]).body.referenceImage,undefined);
});
test('invalid ranges cannot request past the video or outside supported model lengths',()=>{
  const p=project();
  for(const patch of [{start:-1},{start:12},{start:11.5},{duration:.5},{duration:11},{seed:-1},{seed:1.2},{lettering:''},{camera:'custom',motion:''}]){
    const q=setDirection(p,'one',patch);assert.ok(generationPlan(q,q.words[0]).reason,JSON.stringify(patch));
  }
  const plan=generationPlan(p,p.words[2]);assert.equal(plan.end,12);assert.equal(plan.reason,'');
});
