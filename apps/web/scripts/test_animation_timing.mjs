import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL('../src/looks.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});
const {animOf,lookOf,setLookParam,clearLineAnimation}=await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);

test('returning timing to its displayed default restores automatic type/spray timing, preserving other settings',()=>{
  for(const id of ['hud','graffiti','flat-card','dreamy','neon']){
    const p={look:{id,overrides:{font:{hero:'Space Mono'},optics:{glow:.7}}}};
    const original=structuredClone(p),defaults=animOf(lookOf(p));
    let q=setLookParam(p,'in',1.1);q=setLookParam(q,'out',1.2);
    assert.equal(lookOf(q).animIn,1.1);assert.equal(lookOf(q).animOut,1.2);
    q=setLookParam(q,'in',defaults.in);assert.equal(lookOf(q).animOut,1.2);
    q=setLookParam(q,'out',defaults.out);
    assert.deepEqual(q,p);assert.deepEqual(p,original);
  }
});
test('zero remains an explicit cut when the default entrance or exit is nonzero',()=>{
  let p={look:{id:'flat-card'}};p=setLookParam(p,'in',0);p=setLookParam(p,'out',0);
  assert.equal(lookOf(p).animIn,0);assert.equal(lookOf(p).animOut,0);
});
test('timing reset removes both old and current overrides without changing words, wall placement or sibling clips',()=>{
  const p={look:{id:'hud',overrides:{animIn:.7}},words:[{id:'a',lineId:'wall',text:'so',start:1,end:2,placement:'surface',surfaceId:'wall-1'}],
    lineMeta:{wall:{animIn:.6,animOut:.4,u:.2,v:-.1,scale:1.16,appearance:{in:.9,out:.8,layout:'line',font:'Space Mono',glow:.8}},other:{animIn:.5}}};
  const before=structuredClone(p),q=clearLineAnimation(p,['wall']);
  assert.deepEqual(q.lineMeta.wall,{u:.2,v:-.1,scale:1.16,appearance:{layout:'line',font:'Space Mono',glow:.8}});
  assert.equal(q.words,p.words);assert.equal(q.look,p.look);assert.equal(q.lineMeta.other,p.lineMeta.other);
  assert.deepEqual(p,before);assert.deepEqual(clearLineAnimation({lineMeta:{a:{animIn:.4,appearance:{in:.5}}}},['a']),{lineMeta:{}});
});
