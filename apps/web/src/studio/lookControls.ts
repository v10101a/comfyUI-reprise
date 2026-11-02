// UI ownership of properties. Rendering and saved overrides stay backwards compatible.
// Both the composition and selected-text inspectors use this list, inside the existing Studio shell.
import type {Look,LookId,LookParamKey} from '../types';
import {ALL_LOOKS,LOOK_PARAMS,type LookParam} from '../looks';

export type LookControlGroup={id:string;name:string;keys:LookParamKey[]};
const group=(id:string,name:string,keys:LookParamKey[]):LookControlGroup=>({id,name,keys});
const FEATURES:Record<Exclude<LookId,'default'>,LookControlGroup[]>={
  'flat-card':[group('card','Card',['card','pad','cardGap','soft'])],
  'paper-cut':[group('paper','Paper',['outline','soft'])],
  xerox:[group('print','Print',['outline','soft'])],
  dreamy:[group('glow','Glow',['glow','outline','halo','soft']),group('notes','Notes',['boxes','note','noteGlow'])],
  graffiti:[group('paint','Paint',['drips','wall'])],
  neon:[group('light','Light',['glow','flicker','light'])],
  hud:[group('readout','Readout',['glow'])],
  glyph:[group('fill','Letter grid',['fill','cell','backing','glow'])],
  stitch:[],
  ticker:[group('display','Display',['card','glow'])],
  'lens-bound':[group('lens','Lens',['glow','soft','outline','halo'])],
  'red-glow':[group('glow','Glow',['glow','soft'])],
  'grey-noise':[group('notes','Notes',['boxes','note','noteGlow']),group('ink','Ink',['glow','outline','halo','soft'])],
  'night-code':[group('readout','Readout',['glow','soft','halo'])],
  scatter:[group('words','Words',['glow','soft','halo'])],
};
export const lookName=(look:Look)=>ALL_LOOKS.find(l=>l.id===look.id)?.name||'Look';

export function lookControlGroups(look:Look,scope:'look'|'clip'):LookControlGroup[]{
  const common=[group('colour','Colour',['ink','accent']),group('type','Type',['font','body','case','scale'])];
  const features=FEATURES[look.id as Exclude<LookId,'default'>]||[];
  // Dots are an intentional cross-preset effect; the other families retain their own controls.
  const groups=[...common,...features,group('raster','Dots',['dots','dot','gap']),group('wall','On walls',['wall','blend']),group('anim','Timing',['motion','in','out']),group('fields','Music',['flow','voice'])];
  // Clip typography/size/timing already live in the surrounding inspector. Light spill is scene-wide.
  const outside=new Set<LookParamKey>(['ink','font','body','scale','in','out','motion','light','boxes']);
  const seen=new Set<LookParamKey>();
  return groups.map(g=>({...g,keys:g.keys.filter(k=>{
    if(seen.has(k)||scope==='clip'&&(outside.has(k)||k==='accent'&&look.id!=='hud'))return false;
    seen.add(k);return true;
  })})).filter(g=>g.keys.length);
}

export function lookControlParam(look:Look,key:LookParamKey):LookParam{
  const param={...LOOK_PARAMS.find(p=>p.key===key)!};
  if(key==='font'&&(look.layout==='hud'||look.layout==='stack'||look.motion==='marquee'))param.label='Font';
  if(look.id==='hud'&&key==='accent'){param.label='Readout color';param.hint='HUD brackets and readout; dot and connector colors can be set on each clip.';}
  if(look.id==='neon'&&key==='light')param.label='Light spill';
  if(key==='dots')param.optionLabels={off:'Off',square:'Square',round:'Round'};
  return param;
}
