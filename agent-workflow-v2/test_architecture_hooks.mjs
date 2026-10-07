/** Prove the private Pi lifecycle maintains architecture and exposes native skills. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import extension,{commandFor} from './pi-extension.mjs';
import {installToolHooks,installRefreshHooks} from './pi-hooks.mjs';

function setup(t) {
  const folder=mkdtempSync(join(tmpdir(),'pi-architecture-'));
  const keys=['QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_STATE','QWEN_WORKFLOW_SHADOW','QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_STOP_AFTER_PASS'];
  const old=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_PROJECT:folder,
    QWEN_WORKFLOW_STATE:join(folder,'state.json'),QWEN_WORKFLOW_SHADOW:join(folder,'shadow'),
    QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_STOP_AFTER_PASS:'0'});
  writeFileSync(process.env.QWEN_WORKFLOW_STATE,JSON.stringify({before:{root:folder},task:{files:['logic.py','architecture.md']}}));
  t.after(()=>{for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];rmSync(folder,{recursive:true,force:true});});
  return {folder,ctx:{model:{provider:'local-qwen-workflow'},cwd:folder,abort(){}}};
}

test('map adapter preserves section IDs, source hash and independent offsets',()=>{
  assert.deepEqual(commandFor('architecture',[],null,null,20,10),['architecture','--offset','20','--section-offset','10']);
  assert.deepEqual(commandFor('architecture-section',[],'system/rules',null,8000,0,'abc'),['architecture-section','system/rules','--sha256','abc','--offset','8000']);
  assert.deepEqual(commandFor('architecture-search',[],'Game.step',null,10),['architecture-search','Game.step','--offset','10']);
  assert.throws(()=>commandFor('architecture-section',[],'system/rules'),/Supply/);
  for(const query of [undefined,'planned.module: API description']) {
    assert.throws(()=>commandFor('architecture-section',[],query),/section ID.*source_sha256/);
    assert.throws(()=>commandFor('architecture-section',[],query),/provided architecture directly/);
  }
});

test('each successful or partial failed source edit refreshes with frozen state',async t=>{
  const {ctx}=setup(t);const handlers={},calls=[];
  const hash='a'.repeat(64);
  const pi={on:(name,fn)=>{handlers[name]=fn;},exec:async(_python,args)=>{calls.push(args);return {code:0,stdout:JSON.stringify({snapshot:'current',architecture_sections:3,architecture_sha256:hash})};}};
  installRefreshHooks(pi,'python','workflow.py',()=>[]);
  for(const [toolName,isError] of [['write',false],['edit',true]]){
    const result=await handlers.tool_result({toolName,isError,input:{path:'logic.py'},content:[]},ctx);
    assert.equal(result.details.shadow.snapshot,'current');
    const text=result.content.map(block=>block.text||'').join('\n');
    assert.ok(text.includes('architecture.md expected_sha256="'+hash+'"'));
    assert.match(text,/Prepare architecture-update after intervening edits/);
    assert.deepEqual(calls.at(-1).slice(-2),['--state',process.env.QWEN_WORKFLOW_STATE]);
  }
});

test('architecture mutation uses scoped insertion skill and shares edit mutex',async t=>{
  const {ctx}=setup(t);const handlers={},mutations=new Map();
  installToolHooks({on:(n,h)=>{handlers[n]=h;}},mutations);
  assert.match((await handlers.tool_call({toolName:'write',input:{path:'architecture.md'}},ctx)).reason,/Preserve authored architecture/);
  const event={toolName:'skill_use',toolCallId:'insert-one',input:{name:'architecture-update',action:'run',inputs:{}}};
  assert.equal(await handlers.tool_call(event,ctx),undefined);
  assert.equal((await handlers.tool_call({...event,toolCallId:'insert-two'},ctx)).block,true);
  installRefreshHooks({on:(n,h)=>{handlers[n]=h;},exec:async()=>({code:0,stdout:'{"snapshot":"current"}'})},'python','workflow.py',()=>[],mutations);
  await handlers.tool_result({...event,content:[],details:{skill:'architecture-update',action:'run'}},ctx);
  assert.equal(mutations.size,0);
  assert.equal(await handlers.tool_call({...event,toolCallId:'insert-three'},ctx),undefined);
});

test('refresh failure is visible and releases the architecture mutex',async t=>{
  const {ctx}=setup(t);const handlers={},mutations=new Map();
  const event={toolName:'skill_use',toolCallId:'insertion',input:{name:'architecture-update',action:'run'}};
  mutations.set(join(ctx.cwd,'architecture.md'),'insertion');
  installRefreshHooks({on:(n,h)=>{handlers[n]=h;},exec:async()=>({code:1,stderr:'disk full'})},'python','workflow.py',()=>[],mutations);
  const result=await handlers.tool_result({...event,content:[]},ctx);
  assert.equal(result.isError,true);assert.match(result.content[0].text,/completion is blocked/);assert.equal(mutations.size,0);
});

test('required decision evidence prevents premature automatic completion',async t=>{
  const {ctx}=setup(t);process.env.QWEN_WORKFLOW_STOP_AFTER_PASS='1';const handlers={};let aborts=0;
  const context={...ctx,abort:()=>aborts++};
  const pi={on:(n,h)=>{handlers[n]=h;},exec:async(_python,args)=>{
    if(args.includes('refresh'))return {code:0,stdout:JSON.stringify({snapshot:'current',architecture_sha256:'b'.repeat(64)})};
    if(args.includes('test'))return {code:0,stdout:'{"results":[{"exit_code":0}]}'};
    return {code:1,stdout:'{"passed":false,"violations":["Required scoped architecture insertion is missing or stale"]}'};
  }};
  installRefreshHooks(pi,'python','workflow.py',()=>[]);
  const result=await handlers.tool_result({toolName:'edit',input:{path:'logic.py'},content:[]},context);
  assert.equal(result.details.acceptedCompletion,false);assert.equal(aborts,0);
  assert.match(result.content[0].text,/Required scoped architecture insertion/);
  assert.ok(result.content[0].text.includes('architecture.md expected_sha256="'+'b'.repeat(64)+'"'));
});

test('pending edit batch exposes revision but requires preparation after intervening edits',async t=>{
  const {ctx}=setup(t);process.env.QWEN_WORKFLOW_STOP_AFTER_PASS='1';const handlers={};
  const mutations=new Map([['one','1'],['two','2']]);let calls=0;
  installRefreshHooks({on:(n,h)=>{handlers[n]=h;},exec:async()=>{
    calls++;return {code:0,stdout:JSON.stringify({snapshot:'current',architecture_sha256:'c'.repeat(64)})};
  }},'python','workflow.py',()=>[],mutations);
  const result=await handlers.tool_result({toolName:'edit',input:{path:'logic.py'},content:[]},ctx);
  assert.equal(calls,1);
  assert.match(result.content[0].text,/Other edits are finishing/);
  assert.ok(result.content[0].text.includes('architecture.md expected_sha256="'+'c'.repeat(64)+'"'));
  assert.match(result.content[0].text,/Prepare architecture-update after intervening edits/);
});

test('/rebuild executes the fixed native skill with no model request',async t=>{
  const {ctx}=setup(t);const commands={},requests=[],notes=[];
  extension({on(){},registerTool(){},registerCommand:(name,value)=>{commands[name]=value;},
    exec:async(_python,args)=>{requests.push(JSON.parse(readFileSync(args[args.indexOf('--request')+1],'utf8')));return {code:0,stdout:'{}'};}});
  await commands.rebuild.handler('',{...ctx,ui:{notify:(message)=>notes.push(message)}});
  assert.deepEqual(requests,[{action:'prepare',name:'architecture-sync-check'},
    {action:'run',name:'architecture-sync-check',inputs:{action:'rebuild'}}]);
  assert.match(notes[0],/current evidence verified/);
});

test('other providers cannot trigger architecture refresh',async t=>{
  const {ctx}=setup(t);const handlers={};let calls=0;
  installRefreshHooks({on:(n,h)=>{handlers[n]=h;},exec:async()=>{calls++;}},'python','workflow.py',()=>[]);
  assert.equal(await handlers.tool_result({toolName:'edit',content:[]},{...ctx,model:{provider:'unrelated'}}),undefined);
  assert.equal(calls,0);
});

test('owned research publication refreshes parent navigation before planning',async t=>{
  const {folder,ctx}=setup(t);process.env.QWEN_WORKFLOW_ROLE='architect';
  const keys=['QWEN_WORKFLOW_INTERACTIVE','QWEN_WORKFLOW_TOOLKIT'];
  const saved=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  t.after(()=>{for(const key of keys)if(saved[key]===undefined)delete process.env[key];else process.env[key]=saved[key];});
  process.env.QWEN_WORKFLOW_INTERACTIVE='1';process.env.QWEN_WORKFLOW_TOOLKIT=folder;
  const {installInitialPrompt}=await import('./pi-intake.mjs');
  const handlers={},calls=[];
  installInitialPrompt({on:(n,h)=>{handlers[n]=h;},exec:async(_python,args)=>{
    calls.push(args);
    if(args[0].endsWith('initial_prompt.py'))writeFileSync(join(folder,'initial.bridge-result.json'),JSON.stringify({passed:true,refined_prompt:'Ready'}));
    return {code:0,stdout:'{}'};
  }},'python');
  const result=await handlers.input({text:'Plan a feature'},{...ctx,ui:{setStatus(){},notify(){}}});
  assert.equal(result.action,'transform');assert.equal(calls.length,2);
  assert.ok(calls[1].includes('refresh'));assert.ok(calls[1].includes(process.env.QWEN_WORKFLOW_SHADOW));
});
