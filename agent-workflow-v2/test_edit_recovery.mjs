import test from 'node:test';
import assert from 'node:assert/strict';
import {failedEditEvidence} from './pi-edit-recovery.mjs';

test('failed guessed edit returns only its exact affected symbols',async()=>{
  let args;
  const pi={exec:async(_python,argv)=>{args=argv;return {code:0,stdout:'{"symbols":[{"symbol":"begin","source":"function begin(s) {"}]}'};}};
  const event={isError:true,toolName:'edit',input:{path:'app/controller.js',edits:[{oldText:'function begin(s){guess}\nfunction restart(s){guess}'}]}};
  const text=await failedEditEvidence(pi,event,{cwd:'/pilot'},'python','workflow.py',root=>['--project',root]);
  assert.deepEqual(args.slice(-4),['read-symbols','app/controller.js','begin','restart']);
  assert.match(text,/CURRENT SOURCE/);assert.match(text,/line labels are not edit text/);
});

test('successful edits do not retrieve unrelated source',async()=>{
  const pi={exec:()=>{throw Error('Unexpected source read');}};
  assert.equal(await failedEditEvidence(pi,{isError:false,toolName:'edit'},{},'','',()=>[]),'');
});
