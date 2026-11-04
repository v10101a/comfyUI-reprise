import test from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_LAYERS,layersOf,insertLayer,mediaLayer,replaceAsset,dragLayer,layerSourceTime,layerStateAt,setLayerProp,keyAll,unkey,splitMediaLayer} from '../src/layers.ts';

const sky={id:'a1',kind:'video',path:'media/a1_sky.mp4',duration:6,name:'sky'};
const sky2={id:'a2',kind:'video',path:'media/a2_sky.mp4',duration:3,name:'sky 2'};
const tex={id:'a3',kind:'image',path:'media/a3_tex.png',width:64,height:64,name:'tex'};
const project=()=>({id:'t',fps:24,duration:8,assets:[sky,sky2,tex],media:{},words:[],shots:[]});

test('absent layers = the implied stack; first insert makes it explicit around the markers',()=>{
  const p=project();assert.deepEqual(layersOf(p),DEFAULT_LAYERS);
  const l=mediaLayer(sky,p),q=insertLayer(p,l,'under-text');
  assert.deepEqual(q.layers.map(x=>x.kind==='media'?x.assetId:x.id),['plate','a1','text-behind','subject','text-front']);
  const r=insertLayer(q,mediaLayer(tex,q),'top');assert.equal(r.layers.at(-1).assetId,'a3');assert.equal(r.layers.at(-1).out,8);
  const m=insertLayer(r,l,{above:'subject'});assert.deepEqual(m.layers.map(x=>x.kind==='media'?x.assetId:x.id),['plate','text-behind','subject','a1','text-front','a3']);
});
test('replace keeps id, start, transform, keys and effects; clamps the source range',()=>{
  const p=project();let l={...mediaLayer(sky,p,1),in:2,out:5,transform:{x:.1,scale:1.2},blend:'screen',mask:'world',opacity:.5,keys:[{t:0,opacity:0},{t:1,opacity:1}]};
  const q=replaceAsset({...p,layers:[...DEFAULT_LAYERS,l]},l.id,sky2);const n=q.layers.find(x=>x.id===l.id);
  assert.deepEqual({...n,assetId:undefined,name:undefined,in:undefined,out:undefined},{...l,assetId:undefined,name:undefined,in:undefined,out:undefined});
  assert.equal(n.assetId,'a2');assert.equal(n.in,0);assert.equal(n.out,3);
});
test('timing: move, head trim shifts start+in (keys stay on the frame), tail clamps to the source',()=>{
  const l={id:'x',kind:'media',assetId:'a1',start:1,in:0,out:4,keys:[{t:2,x:.5}]};
  assert.equal(dragLayer(l,sky,'move',1.5,24).start,2.5);
  const h=dragLayer(l,sky,'head',1,24);assert.deepEqual([h.start,h.in,h.out,h.keys[0].t],[2,1,4,1]);
  assert.equal(dragLayer(l,sky,'tail',10,24).out,6);
  assert.equal(layerSourceTime(l,.5),undefined);assert.equal(layerSourceTime(l,2),1);assert.equal(layerSourceTime(l,5),undefined);
});
test('keys: static edits until keyed, then smooth between keys and held outside',()=>{
  let l={id:'x',kind:'media',assetId:'a1',start:1,in:0,out:4};
  l=setLayerProp(l,'opacity',.8,0);assert.equal(l.opacity,.8);assert.equal(l.keys,undefined);
  l=keyAll(l,0);l=setLayerProp(l,'x',.4,2);assert.equal(l.keys.length,2);
  assert.equal(layerStateAt(l,1).transform.x,0);assert.equal(layerStateAt(l,3).transform.x,.4);assert.equal(layerStateAt(l,2).transform.x,.2);
  assert.equal(layerStateAt(l,9).transform.x,.4);assert.equal(layerStateAt(l,2).opacity,.8);
  assert.equal(unkey(unkey(l,0),2).keys,null);
});

test('splitting preserves source frames, animated appearance and neighbouring stack order',()=>{
  const p=project(),l={...mediaLayer(sky,p,1),id:'cut',in:1,out:6,mask:'world',blend:'screen',opacity:.6,
    keys:[{t:0,x:0,opacity:.2},{t:4,x:.8,opacity:1}],takes:['a2'],generation:{workflowId:'w',workflows:{w:{inputs:{prompt:'move'}}}}};
  p.layers=[{id:'below',kind:'plate'},l,{id:'above',kind:'text',which:'front'}];const original=structuredClone(p);
  const r=splitMediaLayer(p,'cut',3.01,()=> 'right'),[left,right]=r.project.layers.slice(1,3);
  assert.deepEqual(r.project.layers.map(l=>l.id),['below','cut','right','above']);
  assert.deepEqual([left.start,left.in,left.out,right.start,right.in,right.out],[1,1,3,3,3,6]);
  for(let frame=24;frame<144;frame++){
    const t=frame/24,part=t<3?left:right;
    assert.equal(layerSourceTime(part,t),layerSourceTime(l,t));
    assert.deepEqual(layerStateAt(part,t),layerStateAt(l,t));
  }
  assert.equal(right.mask,'world');assert.equal(right.blend,'screen');assert.deepEqual(right.takes,['a1','a2']);
  right.generation.workflows.w.inputs.prompt='different';right.keys[0].x=2;
  assert.deepEqual(p,original);assert.equal(left.keys[0].x,0);
});
test('splits keep at least a frame on each side and retain linked generated candidates',()=>{
  const p=project(),l={...mediaLayer(sky,p),id:'cut'};p.layers=[l];p.assets.push({id:'generated',source:{layerId:'cut'}});
  for(const at of [NaN,-1,0,6,7])assert.equal(splitMediaLayer(p,'cut',at),null);
  assert.equal(splitMediaLayer(p,'missing',1),null);
  const result=splitMediaLayer(p,'cut',1/24,()=> 'right');assert.equal(result.project.layers[0].out,1/24);
  assert.deepEqual(result.project.layers[1].takes,['a1','generated']);
});

test('topMediaAt picks the visible clip on top under the playhead', async () => {
  const {topMediaAt} = await import('../src/layers.ts');
  const a={id:'a',kind:'media',assetId:'x',start:0,in:0,out:4};
  const b={id:'b',kind:'media',assetId:'y',start:1,in:0,out:2};
  const c={id:'c',kind:'media',assetId:'z',start:1,in:0,out:2,hidden:true};
  const p={layers:[a,b,c,{id:'text-front',kind:'text',which:'front'}]};
  assert.equal(topMediaAt(p,0.5)?.id,'a');
  assert.equal(topMediaAt(p,1.5)?.id,'b');
  assert.equal(topMediaAt(p,3.5)?.id,'a');
  assert.equal(topMediaAt(p,5),undefined);
});
