/** Exercise the recorded contract overflow and Pi's cancellation boundary. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {compactSummary,failingNames,installFixedCompactionHooks} from './pi-compaction-fixed.mjs';
import {taskSummary} from './pi-compaction.mjs';

const source=mkdtempSync(join(tmpdir(),'mypi-contract-'));
const log='✖ deterministic arithmetic boundary test (10ms)\n'+'diagnostic '.repeat(1500);
const gate={passed:false,shadow_snapshot:'current',violations:Array(20).fill('violation '.repeat(70))};
const state={task:{id:'T1',goal:'Repair numeric parsing',files:['numbers.py'],acceptance:[{id:'A',given:'valid input',when:'parse',then:'return numeric value'}],tests:[['python3','-m','unittest']],context:{interfaces:['numbers.py']}},evidence:{results:[{argv:['python3','-m','unittest'],exit_code:1,log:join(source,'test.log')}]}};
writeFileSync(join(source,'task-state.json'),JSON.stringify(state));
writeFileSync(join(source,'test.log'),log);
process.on('exit',()=>rmSync(source,{recursive:true,force:true}));

test('recorded failing contract fits without losing acceptance or tests',()=>{
  const failure={argv:state.evidence.results[0].argv,exit_code:1,
    tail:log.slice(-1500)};
  assert.throws(()=>taskSummary(state.task,gate,[failure]),/compaction budget/);
  const summary=compactSummary(state.task,gate,[{exit_code:1,log:'retained.log',failed_names:failingNames(log)}]);
  assert.ok(summary.length<=12000);
  const data=JSON.parse(summary.slice(summary.indexOf('\n')+1));
  assert.deepEqual(data.task,state.task);
  assert.equal(data.current_gate.passed,false);
  assert.ok(data.failures[0].failed_names.length>0);
});

test('large diagnostics are bounded and omissions are explicit',()=>{
  const g={passed:false,violations:Array(50).fill('x'.repeat(1000)),shadow_snapshot:'current'};
  const data=JSON.parse(compactSummary(state.task,g,[]).split('\n').slice(1).join('\n'));
  assert.equal(data.current_gate.omitted_violations,44);
  assert.equal(data.current_gate.truncated_violation_texts,6);
  assert.deepEqual(data.task.acceptance,state.task.acceptance);
});

test('compaction preserves concrete missing files and prioritizes runnable evidence',()=>{
  const progress={files:[{path:'numbers.py',status:'new',sha256:'current'}],
    pending_files:['test_numbers.py'],tests_status:'not_run',next_action:'Create the missing declared files.'};
  const data=JSON.parse(compactSummary(state.task,{...gate,progress},[]).split('\n').slice(1).join('\n'));
  assert.deepEqual(data.progress,progress);assert.equal(data.next_action,progress.next_action);
  assert.deepEqual(data.task,state.task);
});

test('oversized contract cancels the hook without Pi model fallback',async()=>{
  const folder=mkdtempSync(join(tmpdir(),'pi-compaction-'));
  const old={...process.env};let handler;let aborted=false;
  try {
    writeFileSync(join(folder,'state.json'),JSON.stringify({task:{goal:'x'.repeat(15000)}}));
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_SESSION:folder,
      QWEN_WORKFLOW_STATE:join(folder,'state.json')});
    installFixedCompactionHooks({on:(_name,callback)=>{handler=callback;},
      exec:async()=>({stdout:JSON.stringify(gate),code:1})},'python','workflow.py');
    const result=await handler({preparation:{firstKeptEntryId:'entry',tokensBefore:22000}},
      {model:{provider:'local-qwen-workflow'},abort:()=>{aborted=true;}});
    assert.deepEqual(result,{cancel:true});assert.equal(aborted,true);
    assert.equal(JSON.parse(readFileSync(join(folder,'compaction-error.json'),'utf8')).modelFallbackAllowed,false);
  } finally {
    for (const key of Object.keys(process.env))if (!(key in old))delete process.env[key];
    Object.assign(process.env,old);rmSync(folder,{recursive:true,force:true});
  }
});

test('hook emits a deterministic handoff for the recorded failing task',async()=>{
  const folder=mkdtempSync(join(tmpdir(),'pi-compaction-'));
  const old={...process.env};let handler;
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_SESSION:folder,
      QWEN_WORKFLOW_STATE:join(source,'task-state.json')});
    installFixedCompactionHooks({on:(_name,callback)=>{handler=callback;},
      exec:async()=>({stdout:JSON.stringify(gate),code:1})},'python','workflow.py');
    const result=await handler({preparation:{firstKeptEntryId:'entry',tokensBefore:22000}},
      {model:{provider:'local-qwen-workflow'},abort:()=>{throw new Error('Unexpected abort');}});
    assert.equal(result.compaction.details.modelCall,false);
    assert.equal(result.compaction.details.fullContractPreserved,true);
    assert.equal(result.compaction.firstKeptEntryId,'entry');
    assert.ok(result.compaction.summary.length<=12000);
  } finally {
    for (const key of Object.keys(process.env))if (!(key in old))delete process.env[key];
    Object.assign(process.env,old);rmSync(folder,{recursive:true,force:true});
  }
});

test('a diagnostic-log write failure still cancels instead of model fallback',async()=>{
  const old={...process.env};let handler;let aborted=false;
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_SESSION:'/missing/compaction-log',
      QWEN_WORKFLOW_STATE:'/missing/frozen-task.json'});
    installFixedCompactionHooks({on:(_name,callback)=>{handler=callback;}},'python','workflow.py');
    const result=await handler({}, {model:{provider:'local-qwen-workflow'},abort:()=>{aborted=true;}});
    assert.deepEqual(result,{cancel:true});assert.equal(aborted,true);
  } finally {
    for (const key of Object.keys(process.env))if (!(key in old))delete process.env[key];
    Object.assign(process.env,old);
  }
});
