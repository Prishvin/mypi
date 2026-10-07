/** Exercise the real Python watchdog through Pi lifecycle hooks, without a model. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,existsSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {installExecutionProgressHooks,executionProgress} from './pi-execution-progress.mjs';

const runtime=dirname(fileURLToPath(import.meta.url));
const python=process.env.PYTHON || join(runtime,'.venv/bin/python');

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
