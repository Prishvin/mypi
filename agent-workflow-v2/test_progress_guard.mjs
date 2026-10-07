/** Verify the Pi lifecycle cannot lose missing-file rewrite limits during compaction. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {mutationProgress} from './pi-progress-guard.mjs';
import {installToolHooks,installRefreshHooks} from './pi-hooks.mjs';

function setup(t) {
  const root=mkdtempSync(join(tmpdir(),'mypi-progress-'));
  const old={...process.env};
  Object.assign(process.env,{QWEN_WORKFLOW_SESSION:root,QWEN_WORKFLOW_PROJECT:root,
    QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_STATE:join(root,'task-state.json'),
    QWEN_WORKFLOW_SHADOW:join(root,'shadow'),QWEN_WORKFLOW_STOP_AFTER_PASS:'0'});
  const contract={before:{root},task:{files:['source.py','test_source.py','architecture.md']},
    declared_hashes:{'source.py':null,'test_source.py':null,'architecture.md':null}};
  writeFileSync(process.env.QWEN_WORKFLOW_STATE,JSON.stringify(contract));
  t.after(()=>{for(const k of Object.keys(process.env))if(!(k in old))delete process.env[k];Object.assign(process.env,old);rmSync(root,{recursive:true,force:true});});
  return {root,contract,target:join(root,'source.py')};
}

test('two completed edits pause rewrites; creating required file unlocks repairs',t=>{
  const {root,contract,target}=setup(t);writeFileSync(target,'x=1');
  for(let i=0;i<2;i++) {
    assert.equal(mutationProgress(contract,target),null);
    mutationProgress(contract,target,true);
  }
  const blocked=mutationProgress(contract,target);
  assert.equal(blocked.block,true);assert.equal(blocked.stop,false);
  assert.match(blocked.reason,/test_source.py/);
  assert.equal(mutationProgress(contract,join(root,'test_source.py')),null);
  writeFileSync(join(root,'test_source.py'),'test');
  assert.equal(mutationProgress(contract,target),null);
});

test('journal survives new hook calls and stops repeated ignored instructions',t=>{
  const {root,contract,target}=setup(t);writeFileSync(target,'x=1');
  mutationProgress(contract,target,true);mutationProgress(contract,target,true);
  assert.equal(mutationProgress(contract,target).stop,false);
  assert.equal(mutationProgress(contract,target).stop,false);
  assert.equal(mutationProgress(contract,target).stop,true);
  assert.equal(JSON.parse(readFileSync(join(root,'mutation-progress.json'))).blocked['source.py'],3);
  assert.equal(mutationProgress(contract,join(root,'architecture.md')),null);
});

test('actual tool hooks count successes only and release scoped missing-file creation',async t=>{
  const {root,target}=setup(t),handlers={},mutations=new Map();let aborted=0;
  const ctx={cwd:root,model:{provider:'local-qwen-workflow'},abort:()=>aborted++};
  const pi={on:(name,handler)=>{handlers[name]=handler;},exec:async()=>({code:0,stdout:'{"snapshot":"current"}'})};
  installToolHooks(pi,mutations);installRefreshHooks(pi,'python','workflow.py',()=>[],mutations);
  for(let i=0;i<3;i++) {
    const event={toolName:'write',toolCallId:String(i),input:{path:'source.py'}};
    assert.equal(await handlers.tool_call(event,ctx),undefined);
    writeFileSync(target,'x='+i);
    await handlers.tool_result({...event,isError:i===0,content:[]},ctx);
  }
  const event={toolName:'edit',toolCallId:'blocked',input:{path:'source.py'}};
  assert.equal((await handlers.tool_call(event,ctx)).block,true);
  assert.equal(mutations.size,0);assert.equal(aborted,0);
  const external=await handlers.tool_call({...event,input:{path:'/tmp/unscoped.py'}},ctx);
  assert.match(external.reason,/Allowed files: source.py, test_source.py/);
  assert.equal(await handlers.tool_call({...event,input:{path:'test_source.py'}},ctx),undefined);
});
