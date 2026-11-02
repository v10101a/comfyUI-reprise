import test from 'node:test';
import assert from 'node:assert/strict';
import {copyText,pasteText,splitText,dragTextTiming,nudgeText} from '../src/studio/timelineEdits.ts';

const project=()=>({id:'test',fps:24,duration:10,words:[
  {id:'a',lineId:'one',text:'stay',start:1,end:3,placement:'behind',preset:'none',style:{fill:'#abc'}},
  {id:'b',lineId:'one',text:'here',start:3,end:5,placement:'behind',preset:'none'},
  {id:'c',lineId:'two',text:'now',start:2,end:4,placement:'surface',surfaceId:'wall',preset:'none'},
],lineMeta:{one:{heroWordId:'b',scale:1.4,fill:'#123'},two:{u:.2}},shots:[]});
const ids=()=>{let i=0;return()=>`new-${++i}`;};
test('copy is a snapshot; paste preserves group offsets, styles and metadata with fresh IDs',()=>{
  const p=project(),clip=copyText(p,['one','two']);p.words[0].style.fill='#fff';
  const result=pasteText(p,clip,8,ids());
  assert.equal(result.lineIds.length,2);const added=result.project.words.filter(w=>w.id.startsWith('new-'));
  assert.equal(Math.min(...added.map(w=>w.start)),6);assert.equal(Math.max(...added.map(w=>w.end)),10);
  assert.equal(added.find(w=>w.text==='now').start,7);assert.equal(added.find(w=>w.text==='stay').style.fill,'#abc');
  assert.equal(result.project.lineMeta[added.find(w=>w.text==='here').lineId].heroWordId,added.find(w=>w.text==='here').id);
  assert.equal(added.find(w=>w.text==='now').surfaceId,'wall');assert.equal(p.words.length,3);
});
test('split at a word boundary keeps timing and moves the later word without duplication',()=>{
  const p=project(),r=splitText(p,['one'],3,ids());assert.equal(r.project.words.length,3);
  assert.equal(r.project.words.find(w=>w.id==='a').end,3);assert.equal(r.project.words.find(w=>w.id==='b').lineId,r.lineIds[0]);
  assert.equal(r.project.lineMeta.one.heroWordId,null);assert.equal(r.project.lineMeta[r.lineIds[0]].heroWordId,'b');
  assert.equal(p.words[1].lineId,'one');
});
test('split inside a word preserves both intervals and isolates nested styles',()=>{
  const p=project(),r=splitText(p,['one'],2.01,ids()),copies=r.project.words.filter(w=>w.text==='stay');
  assert.deepEqual(copies.map(w=>[w.start,w.end]),[[1,2],[2,3]]);
  assert.notEqual(copies[0].id,copies[1].id);copies[1].style.fill='#000';assert.equal(p.words[0].style.fill,'#abc');
});
test('empty/outside selections and cross-project paste are no-ops',()=>{
  const p=project();assert.equal(copyText(p,[]),null);assert.equal(splitText(p,['one'],5,ids()),null);
  assert.equal(splitText(p,['one'],0,ids()),null);assert.equal(pasteText({...p,id:'other'},copyText(p,['one']),0,ids()),null);
});
test('body drags move both boundaries equally, including at the project limits',()=>{
  const words=project().words.slice(0,2),before=structuredClone(words);
  for(const [target,delta] of [[2,1],[-10,-1],[20,5]]){
    const moved=dragTextTiming(words,'move',target,10,24);
    assert.deepEqual(moved.map(w=>[w.start,w.end]),words.map(w=>[w.start+delta,w.end+delta]));
    assert.equal(moved[1].start-moved[0].start,2);
  }
  assert.deepEqual(words,before);
});
test('trim handles change only the chosen boundary and retain valid words',()=>{
  const words=project().words.slice(0,2);
  const start=dragTextTiming(words,'start',.5,10,24),end=dragTextTiming(words,'end',6,10,24);
  assert.deepEqual(start.map(w=>[w.start,w.end]),[[.5,3],[3,5]]);
  assert.deepEqual(end.map(w=>[w.start,w.end]),[[1,3],[3,6]]);
  const collapsedStart=dragTextTiming(words,'start',20,10,24),collapsedEnd=dragTextTiming(words,'end',-10,10,24);
  for(const next of [collapsedStart,collapsedEnd])for(const w of next)assert.ok(w.end-w.start>=1/24-1e-6);
  assert.deepEqual(collapsedStart.map(w=>w.end),[3,5]);assert.deepEqual(collapsedEnd.map(w=>w.start),[1,3]);
});
test('nudge moves a line or a single word by whole frames, clamped to the project',()=>{
  const p=project();const r=nudgeText(p,['one'],[],1);
  assert.deepEqual(r.project.words.filter(w=>w.lineId==='one').map(w=>[w.start,w.end]),[[1+1/24,3+1/24].map(x=>+x.toFixed(6)),[3+1/24,5+1/24].map(x=>+x.toFixed(6))]);
  assert.equal(r.project.words.find(w=>w.id==='c').start,2);
  const w=nudgeText(p,[],['a'],-5);assert.equal(w.project.words.find(x=>x.id==='a').start,+(1-5/24).toFixed(6));assert.equal(w.project.words.find(x=>x.id==='b').start,3);
  assert.equal(nudgeText(p,['one'],[],-100).project.words.find(x=>x.id==='a').start,0);
});
