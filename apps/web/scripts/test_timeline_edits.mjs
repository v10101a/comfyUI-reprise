import test from 'node:test';
import assert from 'node:assert/strict';
import {copyText,pasteText,splitText} from '../src/studio/timelineEdits.ts';

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
