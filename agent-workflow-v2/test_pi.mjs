/** Verify workflow rules stay isolated to the named local provider. */
import assert from 'node:assert/strict';
import test from 'node:test';
import extension, { applies, commandFor } from './pi-extension.mjs';
import { active, installRefreshHooks, installPromptHooks, installToolHooks } from './pi-hooks.mjs';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import { fileURLToPath } from 'node:url';
import {spawnSync} from 'node:child_process';

test('source file reads accept the observed fixture call without query and preserve query validation', async()=>{
 const folder=mkdtempSync(join(tmpdir(),'pi-source-page-')),keys=['QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_PROJECT'];
 const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
 try{
  Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_PROJECT:folder});
  writeFileSync(join(folder,'levels.mjs'),'export const LEVELS = [1, 2, 3];\n');
  const registered={};extension({on:()=>{},registerCommand:()=>{},registerTool:t=>{registered[t.name]=t;},
   exec:async(binary,args)=>{const p=spawnSync(binary,args,{encoding:'utf8'});return {code:p.status,stdout:p.stdout,stderr:p.stderr};}});
  const tool=registered.source_query,ctx={model:{provider:'local-qwen-workflow'},cwd:folder};
  assert.equal(tool.parameters.required.includes('query'),false);
  const response=await tool.execute('',{action:'fixture',paths:['levels.mjs']},null,null,ctx);
  const data=JSON.parse(response.content[0].text);assert.equal(data.mode,'project-file');assert.match(data.source,/LEVELS/);
  assert.match(data.note,/action=file/);
  await assert.rejects(tool.execute('',{action:'search',paths:['levels.mjs']},null,null,ctx),/requires a nonempty query/);
  await assert.rejects(tool.execute('',{action:'file',paths:['levels.mjs','other.mjs']},null,null,ctx),/exactly one file/);
 }finally{rmSync(folder,{recursive:true,force:true});for(const k of keys)if(old[k]===undefined)delete process.env[k];else process.env[k]=old[k];}
});

test('native thinking budget is validated without sending unsupported llama.cpp fields', async () => {
  const keys=['QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_THINKING','QWEN_WORKFLOW_REASONING_BUDGET_TOKENS','QWEN_WORKFLOW_INPUT_BUDGET','QWEN_WORKFLOW_REQUEST_LOG'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_SESSION:'/tmp/pi-native-test',QWEN_WORKFLOW_PROJECT:'/repo',QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_THINKING:'on',QWEN_WORKFLOW_REASONING_BUDGET_TOKENS:'4096'});
    delete process.env.QWEN_WORKFLOW_INPUT_BUDGET;delete process.env.QWEN_WORKFLOW_REQUEST_LOG;
    const handlers={};installPromptHooks({on:(n,h)=>{handlers[n]=h;}},fileURLToPath(new URL('.',import.meta.url)));
    const event={payload:{messages:[],max_tokens:32768}},ctx={model:{provider:'local-qwen-workflow'}};
    const payload=await handlers.before_provider_request(event,ctx);
    assert.equal(payload.reasoning_budget_tokens,undefined);assert.equal(payload.max_tokens,32768);
    assert.match(payload.metadata.mtplx_request_id,/^pi-native-test-/);
    assert.equal(payload.chat_template_kwargs.enable_thinking,true);
    process.env.QWEN_WORKFLOW_THINKING='off';
    assert.equal((await handlers.before_provider_request(event,ctx)).reasoning_budget_tokens,undefined);
    assert.equal(await handlers.before_provider_request(event,{model:{provider:'unrelated'}}),undefined);
    process.env.QWEN_WORKFLOW_THINKING='on';process.env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS='bad';
    await assert.rejects(handlers.before_provider_request(event,ctx),/Invalid thinking-token budget/);
  } finally {
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
  }
});

test('automatic completion requires fresh passing tests and gate, with explicit local opt-in', async () => {
  const keys=['QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_STOP_AFTER_PASS','QWEN_WORKFLOW_STATE','QWEN_WORKFLOW_SHADOW','QWEN_WORKFLOW_SESSION'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_STOP_AFTER_PASS:'1',
      QWEN_WORKFLOW_STATE:'/frozen/state.json',QWEN_WORKFLOW_SHADOW:'/shadow'});
    delete process.env.QWEN_WORKFLOW_SESSION;
    const handlers={};let aborted=0,fresh=true,calls=0;
    installRefreshHooks({on:(n,h)=>{handlers[n]=h;},exec:async(_bin,argv)=>{
      calls++;return argv[1]==='check' ? {code:fresh?0:1,stdout:JSON.stringify({passed:fresh,shadow_snapshot:'fresh'})} :
        {code:0,stdout:'{"snapshot":"fresh"}'};
    }},'python','workflow.py',()=>[]);
    const ctx={model:{provider:'local-qwen-workflow'},cwd:'/repo',abort:()=>{aborted++;}};
    const event={toolName:'workflow_test',content:[],details:{testsPassed:true,gatePassed:true}};
    assert.equal((await handlers.tool_result(event,ctx)).details.acceptedCompletion,true);
    assert.equal(aborted,1);assert.equal(calls,2);
    fresh=false;assert.equal(await handlers.tool_result(event,ctx),undefined);assert.equal(aborted,1);
    const prior=calls;
    assert.equal(await handlers.tool_result({...event,details:{testsPassed:false,gatePassed:true}},ctx),undefined);
    assert.equal(await handlers.tool_result(event,{...ctx,model:{provider:'unrelated'}}),undefined);
    process.env.QWEN_WORKFLOW_STOP_AFTER_PASS='0';assert.equal(await handlers.tool_result(event,ctx),undefined);
    assert.equal(calls,prior);assert.equal(aborted,1);
  } finally {
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
  }
});

test('opt-in source edits run frozen tests and stop only after a fresh passing gate', async () => {
  const keys=['QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_STOP_AFTER_PASS','QWEN_WORKFLOW_STATE','QWEN_WORKFLOW_SHADOW','QWEN_WORKFLOW_SESSION'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_STOP_AFTER_PASS:'1',QWEN_WORKFLOW_STATE:'/state',QWEN_WORKFLOW_SHADOW:'/shadow'});
    delete process.env.QWEN_WORKFLOW_SESSION;
    const handlers={};let aborted=0,passing=true;const calls=[];
    installRefreshHooks({on:(n,h)=>{handlers[n]=h;},exec:async(_bin,argv)=>{
      calls.push(argv[1]);
      if(argv[1]==='finalize')return {code:passing?0:1,stdout:JSON.stringify({passed:passing,shadow_snapshot:'new'})};
      return {code:0,stdout:'{"snapshot":"new"}'};
    }},'python','workflow.py',()=>[]);
    const ctx={model:{provider:'local-qwen-workflow'},cwd:'/repo',abort:()=>{aborted++;}};
    const e={toolName:'write',content:[]};
    assert.equal((await handlers.tool_result(e,ctx)).details.acceptedCompletion,true);
    assert.deepEqual(calls,['refresh','finalize']);assert.equal(aborted,1);
    passing=false;assert.equal((await handlers.tool_result(e,ctx)).details.acceptedCompletion,false);assert.equal(aborted,1);
  } finally {
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
  }
});

test('other model providers receive no workflow instructions', async () => {
  const handlers = {};
  let tool;
  extension({ on: (name, handler) => { handlers[name] = handler; }, registerCommand:()=>{}, registerTool: value => { if (value.name === 'project_map') tool = value; } });
  const prompt = { systemPrompt: 'Existing instructions' };
  assert.equal(await handlers.before_agent_start(prompt, { model: { provider: 'openai' } }), undefined);
  const result = await handlers.before_agent_start(prompt, { model: { provider: 'local-qwen-workflow' } });
  assert.ok(result.systemPrompt.startsWith(prompt.systemPrompt));
  assert.ok(result.systemPrompt.includes('LOCAL QWEN CODING WORKFLOW'));
  await assert.rejects(tool.execute('', { action: 'catalog' }, null, null,
    { model: { provider: 'openai' } }), /only/);
});

test('ChatGPT planner is scoped explicitly and cannot expose executor tools', () => {
  const oldPlanner = process.env.QWEN_WORKFLOW_PLANNER;
  const oldRole = process.env.QWEN_WORKFLOW_ROLE;
  try {
    process.env.QWEN_WORKFLOW_PLANNER = 'chatgpt';
    process.env.QWEN_WORKFLOW_ROLE = 'architect';
    assert.equal(active({ provider: 'openai' }), true);
    process.env.QWEN_WORKFLOW_ROLE = 'code';
    assert.equal(active({ provider: 'openai' }), false);
  } finally {
    if (oldPlanner === undefined) delete process.env.QWEN_WORKFLOW_PLANNER;
    else process.env.QWEN_WORKFLOW_PLANNER = oldPlanner;
    if (oldRole === undefined) delete process.env.QWEN_WORKFLOW_ROLE;
    else process.env.QWEN_WORKFLOW_ROLE = oldRole;
  }
});

test('ChatGPT execution requires its own explicit workflow selector', () => {
  const keys=['QWEN_WORKFLOW_EXECUTOR','QWEN_WORKFLOW_ROLE'];
  const old=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  try {
    process.env.QWEN_WORKFLOW_EXECUTOR='chatgpt';process.env.QWEN_WORKFLOW_ROLE='code';
    assert.equal(active({provider:'openai'}),true);
    assert.equal(active({provider:'other'}),false);
    process.env.QWEN_WORKFLOW_EXECUTOR='local';
    assert.equal(active({provider:'openai'}),false);
  }finally{
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
  }
});

test('explicit ChatGPT baseline uses bounded tools and a capped response', async () => {
  const folder=mkdtempSync(join(tmpdir(),'pi-finalize-cloud-'));
  const keys=['QWEN_WORKFLOW_EXECUTOR','QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_STATE','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_OUTPUT_BUDGET','QWEN_WORKFLOW_SESSION'];
  const old=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_EXECUTOR:'chatgpt',QWEN_WORKFLOW_ROLE:'code',
      QWEN_WORKFLOW_STATE:'/frozen/state.json',QWEN_WORKFLOW_PROJECT:'/repo',QWEN_WORKFLOW_OUTPUT_BUDGET:'32768',QWEN_WORKFLOW_SESSION:folder});
    const handlers={},tools={},calls=[];
    extension({on:(name,handler)=>{handlers[name]=handler;},registerCommand:()=>{},registerTool:tool=>{tools[tool.name]=tool;},
      exec:async (_binary,args)=>{calls.push(args);return {code:0,stdout:'{"results":[]}'};}});
    const ctx={model:{provider:'openai'},cwd:'/repo'};
    await tools.source_query.execute('',{action:'search',paths:['app/model.js'],query:'needle'},null,null,ctx);
    assert.ok(calls[0].includes('app/model.js'));
    await tools.workflow_test.execute('',{},null,null,ctx);
    assert.ok(calls[1].includes('finalize'));assert.ok(calls[1].includes('/frozen/state.json'));assert.ok(calls[1].includes('--input'));
    assert.equal(await handlers.tool_call({toolName:'source_query',input:{action:'search',query:'new'}},ctx),undefined);
    const promptHandlers={};
    installPromptHooks({on:(n,h)=>{promptHandlers[n]=h;}},fileURLToPath(new URL('.',import.meta.url)));
    const payload={model:'gpt-6-sol',input:['bounded material'],reasoning:{effort:'medium'}};
    const capped=await promptHandlers.before_provider_request({payload},ctx);
    assert.equal(capped.max_output_tokens,32768);
    assert.deepEqual(capped.input,payload.input);
    assert.deepEqual(capped.reasoning,payload.reasoning);
  }finally{
    rmSync(folder,{recursive:true,force:true});
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
  }
});

test('every edit/write awaits shadow refresh and reports a refresh failure', async () => {
  const handlers = {};
  const original = process.env.QWEN_WORKFLOW_SHADOW;
  process.env.QWEN_WORKFLOW_SHADOW = '/outside/shadow';
  let fail = false;
  const calls = [];
  const pi = { on: (name, handler) => { handlers[name] = handler; },
    exec: async (_binary, args) => { calls.push(args); return fail ?
      { code: 1, stderr: 'disk failure' } : { code: 0, stdout: '{"snapshot":"new-source"}' }; } };
  installRefreshHooks(pi, 'python', 'workflow.py', root => ['--root', root]);
  const ctx = { model: { provider: 'local-qwen-workflow' }, cwd: '/repo' };
  try {
    for (const toolName of ['edit', 'write']) {
      const result = await handlers.tool_result({ toolName, content: [], details: {} }, ctx);
      assert.equal(result.details.shadow.snapshot, 'new-source');
    }
    assert.equal(calls.length, 2);
    fail = true;
    assert.equal((await handlers.tool_result({ toolName: 'edit', content: [] }, ctx)).isError, true);
    assert.equal(await handlers.tool_result({ toolName: 'edit' }, { model: { provider: 'openai' } }), undefined);
  } finally {
    if (original === undefined) delete process.env.QWEN_WORKFLOW_SHADOW;
    else process.env.QWEN_WORKFLOW_SHADOW = original;
  }
});

test('concurrent edits of one file wait until its shadow refresh finishes', async () => {
  const folder=mkdtempSync(join(tmpdir(),'pi-atomic-'));
  const keys=['QWEN_WORKFLOW_STATE','QWEN_WORKFLOW_SHADOW','QWEN_WORKFLOW_ROLE'];
  const old=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  try{
    const state=join(folder,'task.json');
    writeFileSync(state,JSON.stringify({before:{root:folder},task:{files:['model.js']}}));
    Object.assign(process.env,{QWEN_WORKFLOW_STATE:state,QWEN_WORKFLOW_SHADOW:join(folder,'shadow'),QWEN_WORKFLOW_ROLE:'code'});
    const handlers={},mutations=new Map();let release;
    const pi={on:(n,h)=>{handlers[n]=h;},exec:()=>new Promise(resolve=>{release=resolve;})};
    installToolHooks(pi,mutations);installRefreshHooks(pi,'python','workflow.py',()=>[],mutations);
    const ctx={model:{provider:'local-qwen-workflow'},cwd:folder};
    const call=id=>({toolName:'edit',toolCallId:id,input:{path:'model.js'}});
    assert.equal(await handlers.tool_call(call('one'),ctx),undefined);
    const refreshing=handlers.tool_result({...call('one'),content:[]},ctx);
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal((await handlers.tool_call(call('two'),ctx)).block,true);
    release({code:0,stdout:'{"snapshot":"fresh"}'});await refreshing;
    assert.equal(await handlers.tool_call(call('three'),ctx),undefined);
    assert.equal(await handlers.tool_call(call('other'),{...ctx,model:{provider:'unrelated'}}),undefined);
  }finally{
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
    rmSync(folder,{recursive:true,force:true});
  }
});

test('tool requests are argv arrays, with no shell interpolation', () => {
  assert.equal(applies({ provider: 'local-qwen-workflow' }), true);
  assert.deepEqual(commandFor('locate', [], 'x; touch unsafe', ''), ['locate', 'x; touch unsafe']);
  assert.throws(() => commandFor('inspect', [], '', ''), /Supply/);
});

test('repeated identical reads abort the local attempt', async () => {
  const handlers = {};
  installToolHooks({on: (name, handler) => {handlers[name] = handler;}, registerTool: () => {}});
  let aborted = 0;
  const ctx = {model: {provider:'local-qwen-workflow'}, abort: () => {aborted++;}};
  const event = {toolName:'source_query',input:{action:'search',paths:['app/model.js'],query:'export'}};
  for(let i=0;i<3;i++)assert.equal(await handlers.tool_call(event,ctx),undefined);
  assert.equal((await handlers.tool_call(event,ctx)).block,true);
  assert.equal(aborted,1);
});

test('architect tool set blocks source and edits without touching other providers', async () => {
  const handlers = {};
  let active;
  installToolHooks({ on: (name, handler) => { handlers[name] = handler; },
    registerTool: () => {}, setActiveTools: names => { active = names; } });
  const original = process.env.QWEN_WORKFLOW_ROLE;
  process.env.QWEN_WORKFLOW_ROLE = 'architect';
  try {
    const ctx = { model: { provider: 'local-qwen-workflow' } };
    await handlers.session_start({}, ctx);
    assert.deepEqual(active, ['project_map', 'plan_store', 'web_research', 'skill_read','skill_use']);
    assert.equal((await handlers.tool_call({ toolName: 'source_query' }, ctx)).block, true);
    assert.equal(await handlers.tool_call({ toolName: 'read' }, { model: { provider: 'openai' } }), undefined);
  } finally {
    if (original === undefined) delete process.env.QWEN_WORKFLOW_ROLE;
    else process.env.QWEN_WORKFLOW_ROLE = original;
  }
});

test('different searches cannot consume an unbounded task context', async () => {
  const handlers = {};
  installToolHooks({on:(name,handler)=>{handlers[name]=handler;},registerTool:()=>{}});
  const original = process.env.QWEN_WORKFLOW_ROLE;
  process.env.QWEN_WORKFLOW_ROLE = 'code';
  let aborted = 0;
  const ctx = {model:{provider:'local-qwen-workflow'},abort:()=>{aborted++;}};
  try {
    const event = i => ({toolName:'source_query',input:{action:'search',query:String(i)}});
    for(let i=0;i<12;i++)assert.equal(await handlers.tool_call(event(i),ctx),undefined);
    assert.equal((await handlers.tool_call(event(12),ctx)).block,true);
    assert.equal(aborted,0);
    await handlers.tool_call(event(13),ctx);
    assert.equal((await handlers.tool_call(event(14),ctx)).block,true);
    assert.equal(aborted,1);
  } finally {
    if(original===undefined)delete process.env.QWEN_WORKFLOW_ROLE;
    else process.env.QWEN_WORKFLOW_ROLE=original;
  }
});

test('local reasoning choice and explicit thinking override leave other providers alone', async () => {
  const handlers = {};
  const keys = ['QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_REASONING','QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_INPUT_BUDGET','QWEN_WORKFLOW_REQUEST_LOG','QWEN_WORKFLOW_THINKING'];
  const old = Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try {
    process.env.QWEN_WORKFLOW_SESSION='/tmp/pi-native-test';process.env.QWEN_WORKFLOW_PROJECT='/repo';process.env.QWEN_WORKFLOW_REASONING='medium';
    process.env.QWEN_WORKFLOW_ROLE='code';
    delete process.env.QWEN_WORKFLOW_INPUT_BUDGET;delete process.env.QWEN_WORKFLOW_REQUEST_LOG;
    installPromptHooks({on:(n,h)=>{handlers[n]=h;}},fileURLToPath(new URL('.',import.meta.url)));
    const event={payload:{model:'qwen',max_completion_tokens:4096,
      messages:[{role:'assistant',content:'Tool result reviewed',reasoning_content:'Old long reasoning'}]}};
    const payload=await handlers.before_provider_request(event,{model:{provider:'local-qwen-workflow'}});
    assert.equal(payload.reasoning_effort,'medium');
    assert.equal(payload.chat_template_kwargs.reasoning_effort,'medium');
    assert.equal(payload.chat_template_kwargs.enable_thinking,true);
    assert.equal(payload.chat_template_kwargs.preserve_thinking,undefined);
    assert.equal(payload.messages[0].reasoning_content,'Old long reasoning');
    assert.equal(payload.max_completion_tokens,4096);
    assert.equal(payload.temperature,1);
    assert.equal(payload.top_p,.95);
    assert.equal(payload.presence_penalty,0);
    process.env.QWEN_WORKFLOW_REASONING='low';
    const low=await handlers.before_provider_request(event,{model:{provider:'local-qwen-workflow'}});
    assert.equal(low.reasoning_effort,'low');assert.equal(low.chat_template_kwargs.reasoning_effort,'low');
    assert.equal(low.chat_template_kwargs.enable_thinking,true);
    assert.equal(low.max_completion_tokens,payload.max_completion_tokens);
    process.env.QWEN_WORKFLOW_THINKING='off';
    const off=await handlers.before_provider_request(event,{model:{provider:'local-qwen-workflow'}});
    assert.equal(off.chat_template_kwargs.enable_thinking,false);
    assert.equal(off.temperature,.7);
    assert.equal(off.top_p,.8);
    assert.equal(off.presence_penalty,0);
    assert.equal(off.top_k,20);
    assert.equal(off.repeat_penalty,undefined);
    assert.equal(await handlers.before_provider_request(event,{model:{provider:'openai'}}),undefined);
  }finally {
    for(const k of keys)if(old[k]===undefined)delete process.env[k];else process.env[k]=old[k];
  }
});

test('small output cap and thinking reserve are enforced only in the private local provider', async () => {
  const keys=['QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_OUTPUT_BUDGET','QWEN_WORKFLOW_REASONING_BUDGET_TOKENS','QWEN_WORKFLOW_THINKING','QWEN_WORKFLOW_INPUT_BUDGET'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_SESSION:'/tmp/pi-native-test',QWEN_WORKFLOW_PROJECT:'/repo',QWEN_WORKFLOW_OUTPUT_BUDGET:'8192',QWEN_WORKFLOW_REASONING_BUDGET_TOKENS:'1024',QWEN_WORKFLOW_THINKING:'on'});
    delete process.env.QWEN_WORKFLOW_INPUT_BUDGET;
    const handlers={};installPromptHooks({on:(name,fn)=>{handlers[name]=fn;}},fileURLToPath(new URL('.',import.meta.url)));
    const event={payload:{max_tokens:32768,messages:[]}};
    const result=await handlers.before_provider_request(event,{model:{provider:'local-qwen-workflow'}});
    assert.equal(result.max_completion_tokens,8192);assert.equal(result.max_tokens,undefined);
    assert.equal(result.reasoning_budget_tokens,undefined);
    assert.equal(await handlers.before_provider_request(event,{model:{provider:'unrelated'}}),undefined);
    process.env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS='8192';
    await assert.rejects(()=>handlers.before_provider_request(event,{model:{provider:'local-qwen-workflow'}}),/insufficient/);
  } finally {for(const k of keys)if(old[k]===undefined)delete process.env[k];else process.env[k]=old[k];}
});

test('research is bounded and available to an explicitly selected architect', async () => {
  const old=process.env.QWEN_WORKFLOW_ROLE;process.env.QWEN_WORKFLOW_ROLE='architect';
  const handlers={};installToolHooks({on:(name,fn)=>{handlers[name]=fn;}});
  const ctx={model:{provider:'local-qwen-workflow'},abort:()=>{}};
  try {
    const event={toolName:'web_research',input:{action:'search',query:'public documentation'}};
    for(let i=0;i<8;i++)assert.equal(await handlers.tool_call(event,ctx),undefined);
    assert.equal((await handlers.tool_call(event,ctx)).block,true);
    assert.equal(await handlers.tool_call({toolName:'web_research',input:{action:'brief'}},ctx),undefined);
    assert.equal((await handlers.tool_call({toolName:'source_query'},ctx)).block,true);
    assert.equal(await handlers.tool_call(event,{model:{provider:'unrelated'}}),undefined);
  }finally{if(old===undefined)delete process.env.QWEN_WORKFLOW_ROLE;else process.env.QWEN_WORKFLOW_ROLE=old;}
});

test('history A/B preserves active reasoning only in auto and caps are backend-specific',async()=>{
 const keys=['QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_HISTORY_POLICY','QWEN_WORKFLOW_MODEL_VARIANT','QWEN_WORKFLOW_THINKING','QWEN_WORKFLOW_REASONING_BUDGET_TOKENS','QWEN_WORKFLOW_OUTPUT_BUDGET','QWEN_WORKFLOW_INPUT_BUDGET','QWEN_WORKFLOW_REQUEST_LOG'];
 const old=Object.fromEntries(keys.map(k=>[k,process.env[k]])); const oldFetch=globalThis.fetch;
 globalThis.fetch=async()=>({ok:true,json:async()=>({version:1,thinking_cap:'request-local',field:'pi_thinking_cap'})});
 try{
  Object.assign(process.env,{QWEN_WORKFLOW_PROJECT:'/repo',QWEN_WORKFLOW_SESSION:'/tmp/protocol-test',QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_THINKING:'on',QWEN_WORKFLOW_HISTORY_POLICY:'auto',QWEN_WORKFLOW_MODEL_VARIANT:'quality',QWEN_WORKFLOW_REASONING_BUDGET_TOKENS:'4096',QWEN_WORKFLOW_OUTPUT_BUDGET:'16384'});
  delete process.env.QWEN_WORKFLOW_INPUT_BUDGET;delete process.env.QWEN_WORKFLOW_REQUEST_LOG;
  const handlers={};installPromptHooks({on:(name,handler)=>handlers[name]=handler},fileURLToPath(new URL('.',import.meta.url)));
  const event={payload:{messages:[{role:'assistant',reasoning_content:'Active reasoning',content:'Tool call'}]}},ctx={model:{provider:'local-qwen-workflow'}};
  const auto=await handlers.before_provider_request(event,ctx);assert.equal(auto.messages[0].reasoning_content,'Active reasoning');assert.equal(auto.chat_template_kwargs.preserve_thinking,undefined);assert.equal(auto.reasoning_budget_tokens,undefined);assert.equal(auto.metadata.pi_thinking_cap,4096);
  process.env.QWEN_WORKFLOW_HISTORY_POLICY='off';const off=await handlers.before_provider_request(event,ctx);assert.equal(off.messages[0].reasoning_content,'');assert.equal(off.chat_template_kwargs.preserve_thinking,false);
  process.env.QWEN_WORKFLOW_MODEL_VARIANT='27b';const gguf=await handlers.before_provider_request(event,ctx);assert.equal(gguf.reasoning_budget_tokens,4096);
  process.env.QWEN_WORKFLOW_MODEL_VARIANT='gemma';delete process.env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS;const gemma=await handlers.before_provider_request(event,ctx);assert.equal(gemma.reasoning_budget_tokens,undefined);assert.equal(gemma.reasoning_effort,undefined);assert.equal(gemma.chat_template_kwargs.reasoning_effort,undefined);
 }finally{globalThis.fetch=oldFetch;for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];}
});
