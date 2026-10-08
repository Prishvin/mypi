/** Exercise review hooks with the real tokenizer and no provider calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {installRecoveryCompaction} from './pi-recovery-compaction.mjs';
import {installCompactionBoundary} from './pi-compaction-fixed.mjs';
import {rememberSource} from './pi-source-memory.mjs';

function fixture(t,cloud=false){
  const session=mkdtempSync(join(tmpdir(),'mypi-recovery-handoff-')),old={...process.env};
  t.after(()=>{rmSync(session,{recursive:true,force:true});
    for(const key of Object.keys(process.env))if(!(key in old))delete process.env[key];Object.assign(process.env,old);});
  Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_SESSION:session,
    QWEN_WORKFLOW_PROJECT:session,QWEN_WORKFLOW_REPLAN_EVIDENCE:join(session,'evidence.json'),
    QWEN_WORKFLOW_PLAN:join(session,'result.json'),QWEN_WORKFLOW_INPUT_BUDGET:cloud?'196608':'57344',
    QWEN_WORKFLOW_PLANNER:cloud?'chatgpt':'local'});
  const payload=cloud?{instructions:'Actual recovery system instructions',input:[],tools:[]}:
    {messages:[{role:'system',content:'Actual recovery system instructions'}],tools:[]};
  writeFileSync(join(session,'request-budget.json'),JSON.stringify(payload));
  const task={recovery_request:'Immutable acceptance and tests; select one evidence-based recovery action.'};
  const draft={summary:'FAILURE RECOVERY HANDOFF\n'+JSON.stringify({task,
    source_read_budget:{calls_used:2,max_calls:6,bytes_used:800,max_bytes:24000}}),stats:{}};
  const calls=[],handlers={},sent=[];
  const pi={on:(name,fn)=>handlers[name]=fn,sendMessage:(...args)=>sent.push(args),
    exec:async(binary,args)=>{
      calls.push(args[0]);
      if(args[0].endsWith('recovery_handoff.py'))return {code:0,stdout:JSON.stringify(draft)};
      const result=spawnSync(binary,args,{encoding:'utf8',timeout:30000});
      return {code:result.status,stdout:result.stdout,stderr:result.stderr};
    }};
  installCompactionBoundary(pi);
  installRecoveryCompaction(pi,fileURLToPath(new URL('./.venv/bin/python',import.meta.url)),
    fileURLToPath(new URL('./workflow.py',import.meta.url)));
  const ctx={model:{provider:cloud?'openai':'local-qwen-workflow'},abort:()=>{ctx.aborted=true;}};
  return {session,handlers,ctx,calls,task,sent,pi};
}

for(const cloud of [false,true])test(`recovery handoff preserves contract, sources and budget (${cloud?'cloud':'local'})`,async t=>{
  const f=fixture(t,cloud),source='export const observation = 42;\n';
  writeFileSync(join(f.session,'fixture.mjs'),source);
  rememberSource(f.session,f.session,JSON.stringify({path:'fixture.mjs',source,
    sha256:createHash('sha256').update(source).digest('hex')}));
  const {compaction}=await f.handlers.session_before_compact({preparation:{tokensBefore:50000,firstKeptEntryId:'old'}},f.ctx);
  const data=JSON.parse(compaction.summary.split('\n')[1]);
  assert.deepEqual(data.task,f.task);assert.equal(data.source_read_budget.calls_used,2);
  assert.equal(compaction.details.modelCall,false);assert.equal(compaction.firstKeptEntryId,undefined);
  assert.equal(compaction.details.retainedConversationEntries,0);
  assert.equal(compaction.details.sourceMemory.retained,1);assert.match(compaction.summary,/observation = 42/);
  assert.equal(compaction.details.tokenBudget.input_limit,cloud?196608:57344);
  assert.equal(compaction.details.tokenBudget.passed,true);assert.equal(f.ctx.aborted,undefined);
  assert.equal(f.calls.length,2);assert.ok(f.calls.every(x=>x.endsWith('.py')));
  f.handlers.session_compact({compactionEntry:{id:'new',details:compaction.details}},f.ctx);
  assert.equal(f.sent.length,1);assert.deepEqual(f.sent[0][1],{triggerTurn:false});
});

test('changed source is discarded; failed fitting stops without a model fallback',async t=>{
  const f=fixture(t),source='old observation\n';writeFileSync(join(f.session,'fixture.mjs'),source);
  rememberSource(f.session,f.session,JSON.stringify({path:'fixture.mjs',source,
    sha256:createHash('sha256').update(source).digest('hex')}));
  writeFileSync(join(f.session,'fixture.mjs'),'changed\n');
  const first=await f.handlers.session_before_compact({preparation:{tokensBefore:50000}},f.ctx);
  assert.equal(first.compaction.details.sourceMemory.invalidated,1);
  assert.doesNotMatch(first.compaction.summary,/old observation/);
  writeFileSync(join(f.session,'request-budget.json'),'{}');
  const stopped=await f.handlers.session_before_compact({preparation:{tokensBefore:50000}},f.ctx);
  assert.deepEqual(stopped,{cancel:true});assert.equal(f.ctx.aborted,true);
  assert.equal(JSON.parse(readFileSync(join(f.session,'compaction-error.json'))).modelFallbackAllowed,false);
});

test('unbound roles pass through and a published plan never compacts',async t=>{
  const f=fixture(t);delete process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE;
  assert.equal(await f.handlers.session_before_compact({},f.ctx),undefined);assert.equal(f.calls.length,0);
  process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE='bound';
  const plan=process.env.QWEN_WORKFLOW_PLAN,raw='{"published":true}';writeFileSync(plan,raw);
  writeFileSync(join(f.session,'planning-stop.json'),JSON.stringify({plan,
    sha256:createHash('sha256').update(raw).digest('hex')}));
  assert.deepEqual(await f.handlers.session_before_compact({},f.ctx),{cancel:true});
  assert.equal(f.calls.length,0);assert.equal(f.ctx.aborted,true);
});

test('missing diagnostic destination still cancels the fallback',async t=>{
  const f=fixture(t);process.env.QWEN_WORKFLOW_SESSION=join(f.session,'missing');
  const result=await f.handlers.session_before_compact({},f.ctx);
  assert.deepEqual(result,{cancel:true});assert.equal(f.ctx.aborted,true);
});
