import test from 'node:test';
import assert from 'node:assert/strict';
import {packMediaTracks,reorderMedia,stepMediaOrder} from '../src/studio/mediaTracks.ts';
const clip=(id,start,end,extra={})=>({id,kind:'media',assetId:id,start,in:0,out:end-start,...extra});
const ids=rows=>rows.map(r=>r.clips.map(l=>l.id));

test('consecutive visuals and gaps share one row in time order, regardless of stack order',()=>{
  const layers=[clip('late',6,8),clip('early',0,3),clip('middle',3,6),clip('hidden',9,10,{hidden:true})];
  const before=structuredClone(layers);assert.deepEqual(ids(packMediaTracks(layers)),[['early','middle','late','hidden']]);assert.deepEqual(layers,before);
});
test('overlapping visuals retain their compositing order while consecutive foreground clips share a row',()=>{
  const layers=[clip('background',0,10),clip('first',0,3),clip('second',3,6),{id:'text',kind:'text',which:'front'}];
  assert.deepEqual(ids(packMediaTracks(layers)),[['first','second'],['background']]);
  assert.deepEqual(ids(packMediaTracks([...layers,clip('title-card',1,2)])),[['title-card','second'],['first'],['background']]);
});
test('overlap chains preserve pairwise appearance order even when the top and bottom clips do not overlap',()=>{
  const layers=[clip('bottom',2,4),clip('middle',1,3),clip('top',0,2)];
  assert.deepEqual(ids(packMediaTracks(layers)),[['top'],['middle'],['bottom']]);
});
test('dragged clips keep their current row until release and repack compactly afterwards',()=>{
  const moved=[clip('a',0,3),clip('b',2,5)],held=new Map([['a',0],['b',0]]);
  assert.deepEqual(ids(packMediaTracks(moved,held)),[['a','b']]);
  assert.deepEqual(ids(packMediaTracks(moved)),[['b'],['a']]);
  moved[1].start=3;assert.deepEqual(ids(packMediaTracks(moved)),[['a','b']]);
});
test('floating-point seams do not create extra rows and actual frame overlaps do',()=>{
  assert.equal(packMediaTracks([clip('a',0,.1+.2),clip('b',.3,1)]).length,1);
  assert.equal(packMediaTracks([clip('a',0,1),clip('b',1-1/24,2)]).length,2);
  assert.deepEqual(packMediaTracks(undefined),[]);
});

test('reordering a take changes only the stack and preserves unrelated layers and timing',()=>{
 const older=clip('older',.11,5,{in:2,out:6.89,keys:[{t:1,opacity:.5}],generation:{workflowId:'wf'},takes:['a','b']}),newer=clip('newer',0,6);
 const p={layers:[{id:'plate',kind:'plate'},older,newer,{id:'text',kind:'text',which:'front'}]},before=structuredClone(p);
 const q=reorderMedia(p,'older',['newer'],'above');assert.deepEqual(q.layers.map(l=>l.id),['plate','newer','older','text']);assert.equal(q.layers[2],older);assert.deepEqual(p,before);
 assert.deepEqual(ids(packMediaTracks(q.layers)),[['older'],['newer']]);assert.equal(reorderMedia(q,'older',['newer'],'above'),q);
 assert.deepEqual(stepMediaOrder(q,'older','below'),p);
});
test('multiple adjacent takes share a row and collapse again when overlaps are moved away',()=>{
 let p={layers:[clip('older',0,4),clip('newer',2,5),clip('later',5,8)]};
 p=reorderMedia(p,'older',['newer','later'],'above');assert.deepEqual(ids(packMediaTracks(p.layers)),[['older','later'],['newer']]);
 p={...p,layers:p.layers.map(l=>l.id==='newer'?{...l,start:8}:l)};assert.deepEqual(ids(packMediaTracks(p.layers)),[['older','later','newer']]);
});
test('a vertical move can put a clip behind all clips in a packed row',()=>{
 const p={layers:[clip('a',0,3),clip('b',3,6),clip('overlay',0,6)]};const q=reorderMedia(p,'overlay',['a','b'],'below');
 assert.deepEqual(ids(packMediaTracks(q.layers)),[['a','b'],['overlay']]);assert.deepEqual(q.layers.map(l=>l.id),['overlay','a','b']);
 assert.equal(stepMediaOrder(q,'overlay','below'),q);assert.equal(reorderMedia(q,'overlay',['missing'],'above'),q);
});
