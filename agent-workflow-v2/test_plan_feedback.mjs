/** Failed schema responses remain useful without doubling the whole draft in history. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtempSync,readFileSync,rmSync,existsSync,readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {validateToolArguments} from '@earendil-works/pi-ai';
import {installRefreshHooks,installPromptHooks} from './pi-hooks.mjs';
import extension from './pi-extension.mjs';
import {runToolCall} from '../node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-agent-core/dist/agent-loop.js';
import {planFailure} from './pi-plan-feedback.mjs';

function environment(folder){
 const values={QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_SESSION:folder,
  QWEN_WORKFLOW_PROJECT:folder,QWEN_WORKFLOW_PLAN:join(folder,'plan.json'),
  QWEN_WORKFLOW_PLAN_DRAFT:undefined,QWEN_WORKFLOW_PLAN_COVERAGE:undefined};
 const old=Object.fromEntries(Object.keys(values).map(k=>[k,process.env[k]]));
 for(const [k,v] of Object.entries(values))if(v===undefined)delete process.env[k];else process.env[k]=v;
 return ()=>{for(const [k,v] of Object.entries(old))if(v===undefined)delete process.env[k];else process.env[k]=v;};
}

test('plan validation error keeps full original evidence locally and bounds model feedback',async()=>{
 const folder=mkdtempSync(join(tmpdir(),'plan-error-')),restore=environment(folder);
 try{
  const handlers={};installRefreshHooks({on:(name,fn)=>{handlers[name]=fn;}},'python','workflow.py',()=>[]);
  const input={tasks:'X'.repeat(60000)},error='Validation failed: tasks.0 must be object\n\nReceived arguments:\n'+JSON.stringify(input);
  const event={toolName:'plan_store',input,isError:true,content:[{type:'text',text:error}],details:{marker:'kept'}};
  const ctx={model:{provider:'local-qwen-workflow'},abort:()=>{throw Error('Must not mark failed plans accepted');}};
  const result=await handlers.tool_result(event,ctx);
  assert.equal(result.isError,true);assert.equal(result.details.marker,'kept');
  assert.ok(result.content[0].text.length<4000);assert.doesNotMatch(result.content[0].text,/X{20}/);
  assert.match(result.content[0].text,/No plan was accepted/);
  const saved=JSON.parse(readFileSync(result.details.rejectedProposal,'utf8'));
  assert.deepEqual(saved.arguments,input);assert.equal(saved.error,error);
  assert.equal(await handlers.tool_result(event,{...ctx,model:{provider:'unrelated'}}),undefined);
  assert.equal(await handlers.tool_result({...event,toolName:'project_map'},ctx),undefined);
  assert.equal(existsSync(join(folder,'planning-stop.json')),false);
 }finally{restore();rmSync(folder,{recursive:true,force:true});}
});

test('native sparse parse feedback keeps exact evidence and gives the final error plus retry semantics',()=>{
 const folder=mkdtempSync(join(tmpdir(),'sparse-error-')),restore=environment(folder);
 try{
  process.env.QWEN_WORKFLOW_PLAN_DRAFT=join(folder,'bound.json');
  const input={task_updates:'[{"id":"A","steps":["one","two"}]'};
  const error='Traceback (most recent call last):\n'+'  File "runtime.py", line 40\n'.repeat(50)+
    'ValueError: task_updates contains malformed JSON at character 33. Container needs closing array.';
  const result=planFailure({toolName:'plan_store',input,isError:true,content:[{type:'text',text:error}]});
  const text=result.content[0].text;
  assert.match(text,/^ValueError: task_updates contains malformed JSON at character 33/);
  assert.doesNotMatch(text,/Traceback|runtime.py/);
  assert.match(text,/ALL intended edits/);assert.match(text,/not the previous rejected patch/);
  assert.deepEqual(JSON.parse(readFileSync(result.details.rejectedProposal,'utf8')),{arguments:input,error});
 }finally{restore();rmSync(folder,{recursive:true,force:true});}
});

test('real Pi pre-execution validation skips result hooks but context hook safely removes the argument echo',async()=>{
 const folder=mkdtempSync(join(tmpdir(),'plan-schema-error-')),restore=environment(folder);
 try{
  const tools={};extension({on:()=>{},registerCommand:()=>{},registerTool:t=>{tools[t.name]=t;}});
  const toolCall={id:'invalid',name:'plan_store',arguments:{goal:'Build',architecture:'Pure',tasks:[{goal:'X'.repeat(60000)}]}};
  let calls=0;
  const result=await runToolCall(toolCall,{assistantMessage:{role:'assistant',content:[]},
   context:{messages:[],tools:[tools.plan_store]},afterToolCall:()=>{calls++;}});
  assert.equal(calls,0);assert.equal(result.isError,true);
  const message={role:'toolResult',toolName:'plan_store',toolCallId:'invalid',isError:true,content:result.result.content};
  const before=structuredClone(message),handlers={};installPromptHooks({on:(n,h)=>{handlers[n]=h;}},folder);
  const ctx={model:{provider:'local-qwen-workflow'}},event={messages:[{role:'user',content:'Keep user text'},message]};
  const trimmed=await handlers.context(event,ctx);
  assert.ok(JSON.stringify(trimmed.messages[1].content).length<4200);assert.deepEqual(message,before);
  assert.equal(trimmed.messages[0],event.messages[0]);assert.equal(trimmed.messages[1].isError,true);
  const files=readdirSync(folder);await handlers.context(event,ctx);assert.deepEqual(readdirSync(folder),files);
  assert.match(readFileSync(trimmed.messages[1].details.rejectedProposal,'utf8'),/X{100}/);
  assert.equal(await handlers.context(event,{model:{provider:'unrelated'}}),undefined);
 }finally{restore();rmSync(folder,{recursive:true,force:true});}
});

test('actual Pi schema lets literal tasks reach native parsing and malformed JSON yields bounded diagnostic',async()=>{
 const folder=mkdtempSync(join(tmpdir(),'plan-transport-')),restore=environment(folder);
 try{
  const tools={};extension({on:()=>{},registerCommand:()=>{},registerTool:t=>{tools[t.name]=t;},
   exec:async(binary,args)=>{const p=spawnSync(binary,args,{encoding:'utf8'});return {code:p.status,stdout:p.stdout,stderr:p.stderr};}});
  const tool=tools.plan_store,ctx={model:{provider:'local-qwen-workflow'},cwd:folder};
  const malformed='[{"id":"T14","depends_on ["T05"],"description":"'+'x'.repeat(60000)+'"}]';
  const args=validateToolArguments(tool,{name:'plan_store',arguments:{goal:'Build',architecture:'Pure',tasks:malformed}});
  assert.equal(args.tasks,malformed);
  await assert.rejects(tool.execute('bad',args,null,null,ctx),error=>{
   assert.match(error.message,/malformed JSON at character/);assert.ok(error.message.length<4000);return true;
  });
  assert.equal(JSON.parse(readFileSync(join(folder,'plan.json.draft.json'),'utf8')).tasks,malformed);
  assert.equal(existsSync(join(folder,'plan.json')),false);
  const task={id:'T1',goal:'Normalize',files:['x.py'],acceptance:[{id:'A',given:'x',when:'y',then:'z'}],
   tests:[['python3','-m','unittest']],coverage:[{criterion:'A',test:0}],steps:['Implement','Test'],
   assumptions:[],test_strategy:'Behavior and boundary',estimated_changed_lines:40,
   context:{interfaces:[],symbols:[],reference_files:[],max_input_tokens:16384,max_output_tokens:8192,
    estimate:{framework:7168,shadow:0,source:1024,tests:512,history:1024},margin_tokens:2560},
   execution:{timeout_seconds:600,test_timeout_seconds:60,on_failure:'replan'}};
  const good=validateToolArguments(tool,{name:'plan_store',arguments:{goal:'Build',architecture:'Pure',tasks:JSON.stringify([task])}});
  await tool.execute('good',good,null,null,ctx);
  assert.deepEqual(JSON.parse(readFileSync(join(folder,'plan.json'),'utf8')).tasks[0].acceptance,task.acceptance);
 }finally{restore();rmSync(folder,{recursive:true,force:true});}
});
