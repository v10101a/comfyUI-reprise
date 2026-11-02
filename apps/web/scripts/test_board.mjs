import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL('../src/studio/board.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});
const b=await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);
const card=(id,x,y,kind='asset',w=200,h=200)=>({id,x,y,kind,w,h,title:id,assetId:'face',role:'character'});
const project=()=>({id:'p',assets:[{id:'face'},{id:'wardrobe'}],layers:[{id:'shot',kind:'media',assetId:'face',start:2,in:0,out:3,
  generation:{workflowId:'wf',workflows:{wf:{inputs:{prompt:'Night scene'},sources:{face:'face'},variants:2}}}}],
  board:{cards:[card('g',0,0,'group',600,500),card('a',30,70),card('b',700,20)]}});
test('group move carries contained cards once without changing assets or composition',()=>{
  const p=project(),snapshot=structuredClone(p),members=b.groupMembers(p.board.cards,p.board.cards[0]);
  const q=b.moveCards(p,members,140,-20);assert.deepEqual(q.board.cards.map(c=>[c.id,c.x,c.y]),[['g',140,-20],['a',170,50],['b',700,20]]);
  assert.equal(q.assets,p.assets);assert.equal(q.layers,p.layers);assert.deepEqual(p,snapshot);
});
test('zoom preserves the point under the cursor and fit includes negative coordinates',()=>{
  const v={x:120,y:-30,zoom:.8},at={x:330,y:210};const q=b.zoomAt(v,at,1.5);
  const a=b.boardPoint(at,v),c=b.boardPoint(at,q);assert.ok(Math.abs(a.x-c.x)<1e-8&&Math.abs(a.y-c.y)<1e-8);
  const cards=[card('a',-400,-150),card('b',350,200)];const fitted=b.fitBoard(cards,1000,700);
  for(const c of cards){assert.ok(c.x*fitted.zoom+fitted.x>=0);assert.ok((c.x+c.w)*fitted.zoom+fitted.x<=1000);}
});
test('role labels never assign references; explicit assignment changes only the chosen input',()=>{
  const p=project();const tagged=b.updateCard(p,'a',{role:'wardrobe'});assert.equal(tagged.layers,p.layers);
  const q=b.assignReference(p,'shot','wf','costume','wardrobe');assert.deepEqual(q.layers[0].generation.workflows.wf.sources,{face:'face',costume:'wardrobe'});
  assert.equal(q.layers[0].assetId,'face');assert.equal(q.layers[0].start,2);assert.equal(b.assignReference(p,'shot','wf','costume','missing'),p);
});
test('removing a card leaves media and references intact; appending notes retains prompts without duplication',()=>{
  const p=project(),removed=b.removeCard(p,'a');assert.equal(removed.board.cards.length,2);assert.equal(removed.assets,p.assets);assert.equal(removed.layers,p.layers);
  const q=b.appendDirection(p,'shot','wf','prompt','Wind in hair');assert.equal(q.layers[0].generation.workflows.wf.inputs.prompt,'Night scene\n\nWind in hair');
  assert.equal(b.appendDirection(q,'shot','wf','prompt','Wind in hair'),q);
  assert.deepEqual(JSON.parse(JSON.stringify(q)).board,q.board);
});
