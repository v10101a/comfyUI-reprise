import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL('../src/looks.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});
const {lookOf,lineLookOf,setLookParam,setLineParam,setLineMeta,clearLineAppearance,lineIsFilled}=await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);
const project=()=>({id:'test',width:640,height:360,fps:24,duration:5,style:{fontFamily:'Inter',fontSize:.08,fill:'#fff'},look:{id:'glyph'},media:{},analysis:{},shots:[],words:['a','b'].map((id,i)=>({id,lineId:id,text:id,start:i,end:i+1,placement:'overlay',preset:'none',style:{fontFamily:'Inter',fill:'#ff00ff'}})),lineMeta:{a:{hook:true},b:{hook:false}}});

test('no overrides preserves the preset and ignores legacy seeded word styles',()=>{
  const p=project();assert.deepEqual(lineLookOf(p,'a'),lookOf(p));assert.deepEqual(lineLookOf(p,'b'),lookOf(p));
});
test('clip font changes both roles; other clips still inherit later global font edits',()=>{
  const p=project(),before=structuredClone(p);let q=setLineParam(p,['a'],'font','Anton');
  q=setLookParam(q,'font','Space Mono');q=setLookParam(q,'body','Newsreader');
  assert.equal(lineLookOf(q,'a').font.hero,'Anton');assert.equal(lineLookOf(q,'a').font.body,'Anton');
  assert.equal(lineLookOf(q,'b').font.hero,'Space Mono');assert.equal(lineLookOf(q,'b').font.body,'Newsreader');
  q=setLineParam(q,['a'],'font',null);assert.deepEqual(lineLookOf(q,'a'),lookOf(q));assert.deepEqual(p,before);
});
test('clip Person/Background/Off works for verses as well as hooks, without changing siblings',()=>{
  let p=project();assert.equal(lineIsFilled(p,'b'),false);
  p=setLineParam(p,['b'],'fill','world');assert.equal(lineIsFilled(p,'b'),true);
  assert.equal(lineLookOf(p,'a').fill.region,'subject');assert.equal(lineLookOf(p,'b').fill.region,'world');
  p=setLineParam(p,['a'],'fill','off');assert.equal(lineIsFilled(p,'a'),false);
  p=setLineParam(p,['b'],'fill',null);assert.equal(lineIsFilled(p,'b'),false);
});
test('disabled effects stay off when their remembered size is changed; re-enabling restores size',()=>{
  let p=setLineParam(project(),['a'],'cell',.025);p=setLineParam(p,['a'],'fill','off');
  p=setLineParam(p,['a'],'dot',.01);p=setLineParam(p,['a'],'dots','off');
  assert.equal(lineLookOf(p,'a').fill,null);assert.equal(lineLookOf(p,'a').raster,null);
  p=setLineParam(p,['a'],'fill','world');p=setLineParam(p,['a'],'dots','round');
  assert.equal(lineLookOf(p,'a').fill.cell,.025);assert.equal(lineLookOf(p,'a').raster.dot,.01);
});
test('line colour reaches glyph ink and accent; effect overrides retain other inherited optics',()=>{
  let p=setLineMeta(project(),'a',{fill:'#ff3344'});p=setLineParam(p,['a'],'glow',.9);
  assert.equal(lineLookOf(p,'a').palette.text,'#ff3344');assert.equal(lineLookOf(p,'a').palette.accent,'#ff3344');
  assert.equal(lineLookOf(p,'a').optics.glow,.9);assert.equal(lineLookOf(p,'a').optics.chroma,lookOf(p).optics.chroma);
  assert.deepEqual(lineLookOf(p,'b'),lookOf(p));
});
test('group edits and JSON save/load preserve overrides; reset preserves timing, generation and placement',()=>{
  let p=setLineMeta(project(),'a',{u:.3,animIn:.7,generation:{prompt:'stay here'}});
  p=setLineParam(p,['a','b'],'font','Anton');p=setLineParam(p,['a','b'],'backing',.5);
  const saved=JSON.parse(JSON.stringify(p));assert.deepEqual(lineLookOf(saved,'a'),lineLookOf(p,'a'));
  p=clearLineAppearance(saved,['a']);assert.equal(p.lineMeta.a.u,.3);assert.equal(p.lineMeta.a.animIn,.7);
  assert.equal(p.lineMeta.a.generation.prompt,'stay here');assert.equal(p.lineMeta.b.appearance.font,'Anton');
  assert.deepEqual(lineLookOf(p,'a'),lookOf(p));
});
