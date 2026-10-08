/** Reading a failed gate is useful evidence, bound to the active task. */
import test from 'node:test';
import assert from 'node:assert/strict';
import extension,{commandFor} from './pi-extension.mjs';

test('gate defaults to the bound state and rejects another task',t=>{
  const old=process.env.QWEN_WORKFLOW_STATE;
  t.after(()=>{if(old===undefined)delete process.env.QWEN_WORKFLOW_STATE;else process.env.QWEN_WORKFLOW_STATE=old;});
  process.env.QWEN_WORKFLOW_STATE='/bound/state.json';
  assert.deepEqual(commandFor('gate'),['check','--state','/bound/state.json']);
  assert.deepEqual(commandFor('gate',undefined,undefined,'/bound/./state.json'),['check','--state','/bound/state.json']);
  assert.throws(()=>commandFor('gate',undefined,undefined,'/other/state.json'),/frozen task/);
  delete process.env.QWEN_WORKFLOW_STATE;
  assert.throws(()=>commandFor('gate'),/No frozen task/);
  assert.deepEqual(commandFor('gate',undefined,undefined,'/explicit/state.json'),['check','--state','/explicit/state.json']);
});

test('failed acceptance remains structured evidence while malformed command failures stay errors',async t=>{
  const old=process.env.QWEN_WORKFLOW_STATE;
  t.after(()=>{if(old===undefined)delete process.env.QWEN_WORKFLOW_STATE;else process.env.QWEN_WORKFLOW_STATE=old;});
  process.env.QWEN_WORKFLOW_STATE='/bound/state.json';
  let response={code:1,stdout:JSON.stringify({passed:false,violations:['Tests are not yet green'],patch_lines:310}),stderr:''};
  const tools={},calls=[];
  extension({on:()=>{},registerCommand:()=>{},registerTool:tool=>tools[tool.name]=tool,
    exec:async(_bin,args)=>{calls.push(args);return response;}});
  const ctx={model:{provider:'local-qwen-workflow'},cwd:'/project'};
  const run=params=>tools.project_map.execute('gate',params,null,null,ctx);
  const result=await run({action:'gate'});
  assert.equal(result.isError,undefined);assert.equal(result.details.gatePassed,false);
  assert.equal(JSON.parse(result.content[0].text).patch_lines,310);
  assert.deepEqual(calls[0].slice(-3),['check','--state','/bound/state.json']);
  const before=calls.length;
  await assert.rejects(run({action:'gate',state:'/other/state.json'}),/frozen task/);
  assert.equal(calls.length,before);
  for(const value of [{code:1,stdout:'bad JSON',stderr:''},
                     {code:1,stdout:'{"passed":false}',stderr:''},
                     {code:2,stdout:'{"passed":false,"violations":[]}',stderr:''}]){
    response=value;await assert.rejects(run({action:'gate'}));
  }
  response={code:0,stdout:'{"passed":true,"violations":[]}',stderr:''};
  assert.equal((await run({action:'gate'})).details.gatePassed,true);
  response={code:1,stdout:'{"passed":false,"violations":[]}',stderr:''};
  await assert.rejects(run({action:'inspect',paths:['unit.mjs']}));
});
