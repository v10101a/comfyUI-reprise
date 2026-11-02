import test from 'node:test';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {build}=createRequire(import.meta.resolve('vite'))('esbuild');
const {outputFiles}=await build({entryPoints:[fileURLToPath(new URL('../src/placement.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});
const {autoPlace,OccupancySource}=await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`);
const occupancy={fps:24,cols:8,rows:8,step:1,frames:Array.from({length:24},(_,f)=>Buffer.from(Array.from({length:64},(_,i)=>(i*17+f*23)%256)).toString('base64'))};
const source=()=>new OccupancySource(occupancy,undefined,24);
test('warm placement coverage matches fresh calculations after timing, size, hints and obstacle edits',()=>{
  const warm=source();
  const reqs=[{key:'hero',w:.32,h:.12,f0:0,f1:8,tolerance:.1,canPromote:true},{key:'sat',w:.18,h:.08,f0:3,f1:15,tolerance:.03,strict:true,avoidKey:'hero'}];
  for(let i=0;i<10;i++){
    const edited=structuredClone(reqs);
    if(i%3===0)edited[0].f1+=i;
    if(i%3===1)edited[0].w+=i*.01;
    edited[1].hint={x:.1+i*.07,y:.8};
    const obstacles=[{box:[.1,.1,.3+i*.02,.3],f0:4,f1:12}];
    const args=[1.1,obstacles,[.06,.07]];
    assert.deepEqual([...autoPlace(edited,warm,...args)],[...autoPlace(edited,source(),...args)]);
  }
});
