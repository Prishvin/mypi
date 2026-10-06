/** Verify phase permissions, store-and-stop, and real /remember command dispatch. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {active,installToolHooks,installPromptHooks,installRefreshHooks} from './pi-hooks.mjs';
import {registerRemember,latestOutput} from './pi-remember.mjs';
import {installInitialPrompt} from './pi-intake.mjs';
import {registerRoleSelection} from './pi-role-selection.mjs';

const base=fileURLToPath(new URL('.',import.meta.url));
function environment(values) {
  const prior=Object.fromEntries(Object.keys(values).map(k=>[k,process.env[k]]));
  Object.assign(process.env,values);
  return ()=>{for(const [k,v] of Object.entries(prior))if(v===undefined)delete process.env[k];else process.env[k]=v;};
}

test('planner switches its actual model/effort while reviewer selection leaves it alone',async()=>{
  const folder=mkdtempSync(join(tmpdir(),'pi-select-'));
  const restore=environment({QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLANNER:'chatgpt',
    QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_PROJECT:folder,QWEN_WORKFLOW_TOOLKIT:base});
  const commands={},models=[],levels=[],calls=[];
  const pi={registerCommand:(n,c)=>{commands[n]=c;},setModel:async model=>{models.push(model);return true;},
    setThinkingLevel:v=>levels.push(v),exec:async(binary,args)=>{calls.push([binary,args]);return {code:0,stdout:'{}'};}};
  const ctx={model:{provider:'openai'},hasUI:false,waitForIdle:async()=>{},ui:{notify:()=>{}},modelRegistry:{find:(provider,id)=>({provider,id})}};
  try {
    registerRoleSelection(pi,'python');
    await commands.planner.handler('local',ctx);
    assert.deepEqual(models[0],{provider:'local-qwen-workflow',id:'mtplx-quality'});
    assert.equal(levels[0],'medium');assert.equal(process.env.QWEN_WORKFLOW_PLANNER,'local');
    ctx.model={provider:'local-qwen-workflow'};
    await commands.reviewer.handler('chatgpt',ctx);assert.equal(models.length,1);
    await commands.planner.handler('chatgpt',ctx);
    assert.deepEqual(models[1],{provider:'openai',id:'gpt-6.1-sol'});assert.equal(levels[1],'xhigh');
    assert.ok(calls.some(([,a])=>a.includes('reviewer')));
  }finally{restore();delete process.env.QWEN_WORKFLOW_REASONING;delete process.env.QWEN_WORKFLOW_THINKING;rmSync(folder,{recursive:true,force:true});}
});

test('first interactive request has at most two UI questions, then transforms once',async()=>{
  const folder=mkdtempSync(join(tmpdir(),'pi-intake-ui-'));
  const restore=environment({QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLANNER:'chatgpt',
    QWEN_WORKFLOW_INTERACTIVE:'1',QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_PROJECT:folder,QWEN_WORKFLOW_TOOLKIT:base});
  const handlers={};let calls=0,questions=0;
  const pi={on:(n,h)=>{handlers[n]=h;},exec:async()=>{
    calls++;
    const result=calls<3?{passed:false,stage:'awaiting_clarification',intake:{decision:{question:{text:'Question '+calls,options:[]}}}}:
      {passed:true,refined_prompt:'One combined prompt with both answers'};
    writeFileSync(join(folder,'initial.bridge-result.json'),JSON.stringify(result));return {code:0};
  }};
  const ctx={model:{provider:'openai'},hasUI:true,ui:{setStatus:()=>{},notify:()=>{},input:async()=>{questions++;return 'Answer '+questions;}}};
  try {
    installInitialPrompt(pi,'python');
    const result=await handlers.input({text:'Original ambiguous request'},ctx);
    assert.equal(result.action,'transform');assert.equal(questions,2);assert.equal(calls,3);
    assert.deepEqual(JSON.parse(readFileSync(join(folder,'initial-answers.json'))),['Answer 1','Answer 2']);
    assert.equal(await handlers.input({text:'Next architecture message'},ctx),undefined);
    assert.equal(calls,3);
  }finally{restore();rmSync(folder,{recursive:true,force:true});}
});

test('intake has only its store; research cannot read implementation or bypass search skills',async()=>{
  const restore=environment({QWEN_WORKFLOW_ROLE:'intake',QWEN_WORKFLOW_PLANNER:'chatgpt'});
  const handlers={};let tools=[];
  const pi={on:(n,h)=>{handlers[n]=h;},setActiveTools:v=>{tools=v;}};
  const ctx={model:{provider:'openai'},abort:()=>{}};
  try {
    installToolHooks(pi);assert.equal(active(ctx.model),true);
    await handlers.session_start({},ctx);assert.deepEqual(tools,['intake_store']);
    assert.equal((await handlers.tool_call({toolName:'skill_use',input:{action:'run'}},ctx)).block,true);
    process.env.QWEN_WORKFLOW_ROLE='memory';await handlers.session_start({},ctx);
    assert.deepEqual(tools,['memory_store']);
    for(const name of ['project_map','source_query','edit','web_research'])
      assert.equal((await handlers.tool_call({toolName:name},ctx)).block,true);
    process.env.QWEN_WORKFLOW_ROLE='research';await handlers.session_start({},ctx);
    assert.ok(tools.includes('knowledge_store'));assert.ok(!tools.includes('source_query'));
    for(const event of [{toolName:'edit'},{toolName:'source_query'},
      {toolName:'project_map',input:{action:'inspect'}},{toolName:'web_research',input:{action:'search'}}])
      assert.equal((await handlers.tool_call(event,ctx)).block,true);
    for(let i=0;i<3;i++) assert.equal(await handlers.tool_call({toolName:'skill_use',input:{action:'run',name:'duckduckgo-search'}},ctx),undefined);
    assert.equal((await handlers.tool_call({toolName:'skill_use',input:{action:'run',name:'duckduckgo-search'}},ctx)).block,true);
    assert.equal(await handlers.tool_call({toolName:'edit'},{model:{provider:'unrelated'}}),undefined);
  }finally{restore();}
});

test('initial role prompts omit frozen coding rules and phase completion is digest-bound',async()=>{
  const folder=mkdtempSync(join(tmpdir(),'pi-phase-'));
  const output=join(folder,'draft.json');writeFileSync(output,'{"version":1,"mode":"ready"}');
  const restore=environment({QWEN_WORKFLOW_ROLE:'intake',QWEN_WORKFLOW_PLANNER:'chatgpt',
    QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_PHASE_OUTPUT:output});
  const handlers={};let aborted=0;
  const pi={on:(n,h)=>{handlers[n]=h;}};
  const ctx={model:{provider:'openai'},abort:()=>{aborted++;}};
  try {
    installPromptHooks(pi,base);
    const prompt=await handlers.before_agent_start({systemPrompt:'System'},ctx);
    assert.match(prompt.systemPrompt,/Maximum TWO rounds/);
    assert.ok(!prompt.systemPrompt.includes('LOCAL QWEN CODING WORKFLOW'));
    installRefreshHooks(pi,'python','workflow.py',()=>[]);
    await handlers.tool_result({toolName:'intake_store',isError:true,details:{phase:'intake',output}},ctx);
    assert.equal(aborted,0);
    await handlers.tool_result({toolName:'intake_store',content:[],details:{phase:'intake',output}},ctx);
    assert.equal(aborted,1);
    const marker=JSON.parse(readFileSync(join(folder,'intake-stop.json')));
    assert.equal(marker.output,output);assert.equal(marker.sha256.length,64);
  }finally{restore();rmSync(folder,{recursive:true,force:true});}
});

test('/remember selects completed text and requests fresh distillation with the active provider',async()=>{
  const folder=mkdtempSync(join(tmpdir(),'pi-remember-'));
  const restore=environment({QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLANNER:'chatgpt',
    QWEN_WORKFLOW_PROJECT:folder,QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_SHADOW:join(folder,'shadow'),
    QWEN_WORKFLOW_TOOLKIT:base});
  const branch=[{type:'message',message:{role:'assistant',stopReason:'stop',content:[{type:'thinking',thinking:'Private thought'},
    {type:'text',text:'Use a pure parser and separate renderer.'}]}},
    {type:'message',message:{role:'assistant',stopReason:'aborted',content:[{type:'text',text:'Partial answer'}]}}];
  let command,notified,calls=[];
  const pi={registerCommand:(name,def)=>{assert.equal(name,'remember');command=def;},exec:async(binary,args)=>{
    calls.push(args);return {code:0,stdout:'{"summary":"- Separate parsing from rendering."}',stderr:''};}};
  try {
    assert.equal(latestOutput(branch),'Use a pure parser and separate renderer.');
    registerRemember(pi,join(base,'.venv/bin/python'),base);
    const ctx={model:{provider:'openai'},waitForIdle:async()=>{},sessionManager:{getBranch:()=>branch},ui:{notify:v=>{notified=v;}}};
    await command.handler('',ctx);
    assert.equal(readFileSync(join(folder,'remember-input.txt'),'utf8'),'Use a pure parser and separate renderer.');
    assert.equal(calls[0].at(-1),'chatgpt');assert.match(notified,/Distilled essentials/);
    ctx.model={provider:'local-qwen-workflow'};await command.handler('Explicit selected note',ctx);
    assert.equal(calls[1].at(-1),'qwen');assert.equal(calls.length,2);
  }finally{restore();rmSync(folder,{recursive:true,force:true});}
});
