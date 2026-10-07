/** Exercise the real Python watchdog through Pi lifecycle hooks, without a model. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,existsSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {installExecutionProgressHooks,executionProgress,progressNotice} from './pi-execution-progress.mjs';

const runtime=dirname(fileURLToPath(import.meta.url));
const python=process.env.PYTHON || join(runtime,'.venv/bin/python');

test('request-local notices stay small even when the journal is large',()=>{
  const brief={status:'warning',rounds_without_progress:2,compactions_without_progress:1,
    repeated_read_count:2,recent_tools:Array(100).fill({query:'PRIVATE_SOURCE'.repeat(100)}),
    tests:Array(100).fill({observations:['PRIVATE_TEST'.repeat(100)]}),
    deadline:{near_deadline:true,remaining_seconds:239}};
  const before=JSON.stringify(brief),text=progressNotice(brief);
  assert.ok(text.length<800);assert.doesNotMatch(text,/PRIVATE_/);
  assert.match(text,/239 seconds/);assert.match(text,/"status":"warning"/);
  assert.equal(JSON.stringify(brief),before);
});

function setup(t) {
  const session=mkdtempSync(join(tmpdir(),'pi-stagnation-')),old={...process.env};
  Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_SESSION:session,
    QWEN_WORKFLOW_STATE:join(session,'task-state.json')});
  writeFileSync(join(session,'task-state.json'),JSON.stringify({before:{root:session},task:{id:'T1',files:['source.py']}}));
  writeFileSync(join(session,'source.py'),'PRIVATE_SOURCE');
  const handlers={};let aborted=0,calls=0;
  const ctx={model:{provider:'local-qwen-workflow'},abort:()=>aborted++};
  const pi={on:(name,fn)=>{handlers[name]=fn;},exec:async(binary,args)=>{
    calls++;return {code:0,stdout:execFileSync(binary,args,{encoding:'utf8'})};}};
  installExecutionProgressHooks(pi,python,runtime);
  t.after(()=>{for(const k of Object.keys(process.env))if(!(k in old))delete process.env[k];
    Object.assign(process.env,old);rmSync(session,{recursive:true,force:true});});
  return {session,handlers,ctx,pi,aborted:()=>aborted,calls:()=>calls};
}

test('warning is injected then next provider call is prevented on durable stop',async t=>{
  const {session,handlers:h,ctx,aborted}=setup(t),input={messages:[]};
  assert.equal(await h.context(input,ctx),undefined);
  for(let i=1;i<=4;i++) {
    h.message_end({message:{role:'assistant'}},ctx);
    if(i===4)await assert.rejects(h.context(input,ctx),/no_progress/);
    else {
      const result=await h.context(input,ctx);
      if(i>=2)assert.match(result.messages[0].content[0].text,/No measured progress/);
    }
  }
  assert.equal(input.messages.length,0);assert.equal(aborted(),1);
  assert.equal(JSON.parse(readFileSync(join(session,'progress-stop.json'))).reason,'no_progress');
});

test('tool journal excludes source/reasoning and retains relevant selectors/errors',async t=>{
  const {session,handlers:h,ctx}=setup(t);
  h.message_end({message:{role:'user',content:'PRIVATE_USER'}},ctx);
  h.tool_execution_start({toolCallId:'a',args:{path:'source.py',oldText:'PRIVATE_SOURCE',newText:'PRIVATE_EDIT'}},ctx);
  h.tool_execution_end({toolCallId:'a',toolName:'edit',isError:true,result:{content:[
    {type:'text',text:'Traceback\n PRIVATE_TRACE\nValueError: mismatch\nReceived arguments: PRIVATE_ARGS'}]}},ctx);
  const journal=readFileSync(join(session,'execution-events.jsonl'),'utf8');
  assert.doesNotMatch(journal,/PRIVATE_/);assert.match(journal,/ValueError: mismatch/);
  assert.deepEqual(JSON.parse(journal).selector,{path:'source.py'});
  h.tool_execution_end({toolCallId:'b',toolName:'edit',isError:true,result:{content:[
    {type:'text',text:'Validation failed for tool "edit":\n  - path: must be present\nReceived arguments: PRIVATE_ARGS'}]}},ctx);
  assert.match(readFileSync(join(session,'execution-events.jsonl'),'utf8'),/path: must be present/);
  assert.doesNotMatch(readFileSync(join(session,'execution-events.jsonl'),'utf8'),/PRIVATE_/);
});

test('distinct successful reads have bounded grace through real Pi hooks',async t=>{
  const {handlers:h,ctx,aborted}=setup(t);
  await h.context({messages:[]},ctx);
  for(let i=1;i<=8;i++) {
    h.message_end({message:{role:'assistant'}},ctx);
    h.tool_execution_start({toolCallId:String(i),args:{action:'file',paths:['source.py'],offset:i*20}},ctx);
    h.tool_execution_end({toolCallId:String(i),toolName:'source_query',isError:false,result:{content:[]}},ctx);
    if(i===8)await assert.rejects(h.context({messages:[]},ctx),/no_progress/);
    else await h.context({messages:[]},ctx);
  }
  assert.equal(aborted(),1);
});

test('chat/reviewer/Codex sessions do not run this watchdog',async t=>{
  const x=setup(t);
  for(const role of ['chat','architect','reviewer','inspect']) {
    process.env.QWEN_WORKFLOW_ROLE=role;
    assert.equal(await x.handlers.context({messages:[]},x.ctx),undefined);
  }
  process.env.QWEN_WORKFLOW_ROLE='code';x.ctx.model.provider='unrelated';
  assert.equal(await x.handlers.context({messages:[]},x.ctx),undefined);assert.equal(x.calls(),0);
});

test('compaction checkpoint observes recent errors and stops persistent unchanged rounds',async t=>{
  const x=setup(t);await x.handlers.context({messages:[]},x.ctx);
  for(let i=0;i<3;i++) {
    x.handlers.message_end({message:{role:'assistant'}},x.ctx);
    const brief=await executionProgress(x.pi,python,runtime,x.ctx,true);
    assert.equal(brief.status,i===2?'stop':i===1?'warning':'continue');
  }
  assert.equal(x.aborted(),1);
});

test('a watchdog failure aborts visibly instead of silently disabling protection',async t=>{
  const x=setup(t);x.pi.exec=async()=>({code:1,stderr:'broken journal'});
  await assert.rejects(x.handlers.context({messages:[]},x.ctx),/broken journal/);
  assert.equal(x.aborted(),1);assert.equal(existsSync(join(x.session,'progress-error.json')),true);
});

test('near deadline adds a factual notice even with fresh progress, without abort or input mutation',async t=>{
  const x=setup(t),state=join(x.session,'task-state.json');
  writeFileSync(join(x.session,'launch.json'),JSON.stringify({role:'code',project:x.session,state,timeout_seconds:900}));
  writeFileSync(join(x.session,'process.json'),JSON.stringify({started_epoch:Date.now()/1000-700}));
  const input={messages:[{role:'user',content:'original'}]};
  const result=await x.handlers.context(input,x.ctx);
  assert.equal(input.messages.length,1);assert.equal(result.messages.length,2);
  assert.match(result.messages[1].content[0].text,/ATTEMPT DEADLINE: \d+ seconds remain/);
  assert.match(result.messages[1].content[0].text,/Preserve all acceptance checks/);
  assert.match(result.messages[1].content[0].text,/"status":"continue"/);
  assert.equal(x.aborted(),0);assert.equal(existsSync(join(x.session,'progress-stop.json')),false);
});

test('early clock is recorded but does not add routine prompt noise',async t=>{
  const x=setup(t);
  writeFileSync(join(x.session,'launch.json'),JSON.stringify({role:'code',project:x.session,
    state:join(x.session,'task-state.json'),timeout_seconds:900}));
  writeFileSync(join(x.session,'process.json'),JSON.stringify({started_epoch:Date.now()/1000-10}));
  assert.equal(await x.handlers.context({messages:[]},x.ctx),undefined);
  assert.equal(JSON.parse(readFileSync(join(x.session,'execution-progress.json'))).brief.deadline.near_deadline,false);
  assert.equal(x.aborted(),0);
});
