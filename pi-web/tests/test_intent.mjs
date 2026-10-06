import test from 'node:test';import assert from 'node:assert/strict';import {mkdtempSync,readFileSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {registerChat} from '../../agent-workflow-v2/pi-chat.mjs';
import {installToolHooks} from '../../agent-workflow-v2/pi-hooks.mjs';
import extension from '../../agent-workflow-v2/pi-extension.mjs';

test('planner advertises and enforces the executable V3 contract',async()=>{
 const saved={...process.env};const tools={};
 try{
  process.env.QWEN_WORKFLOW_ROLE='architect';
  extension({on:()=>{},registerCommand:()=>{},registerTool:t=>tools[t.name]=t});
  assert.equal(tools.plan_store.parameters.properties.plan_version.const,3);
  await assert.rejects(tools.plan_store.execute('x',{plan_version:2},null,null,{model:{provider:'local-qwen-workflow'}}),/plan_version 3/);
 }finally{process.env=saved;}
});

test('chat handoff persists a request and intentional stop; cannot run in another role',async()=>{
 const folder=mkdtempSync(join(tmpdir(),'web-intent-'));const saved={...process.env};const handlers={},tools={};
 try{process.env.QWEN_WORKFLOW_ROLE='chat';process.env.QWEN_WORKFLOW_SESSION=folder;let stopped=false;
 registerChat({registerTool:t=>tools[t.name]=t,on:(name,fn)=>handlers[name]=fn});
 const result=await tools.development_request.execute('x',{request:'Implement a parser'},null,null,{});
 assert.equal(JSON.parse(readFileSync(join(folder,'development-request.json'))).request,'Implement a parser');
 handlers.tool_result({details:result.details,isError:false},{abort:()=>stopped=true});assert.equal(stopped,true);
 process.env.QWEN_WORKFLOW_ROLE='code';await assert.rejects(tools.development_request.execute('x',{request:'bad'},null,null,{}));
 }finally{process.env=saved;rmSync(folder,{recursive:true,force:true});}
});
test('chat may research but cannot edit, run shell or save a development plan directly',async()=>{
 const saved={...process.env};const handlers={};try{process.env.QWEN_WORKFLOW_ROLE='chat';
 installToolHooks({on:(name,fn)=>handlers[name]=fn});const ctx={model:{provider:'local-qwen-workflow'}};
 for(const name of ['edit','write','bash','plan_store','source_query','development_request'])assert.equal((await handlers.tool_call({toolName:name,input:{}},ctx)).block,true);
 for(const name of ['skill_use','skill_read'])assert.equal(await handlers.tool_call({toolName:name,input:{}},ctx),undefined);
 }finally{process.env=saved;}
});

test('inspection may retrieve source but cannot mutate, execute tests or change branches',async()=>{
 const saved={...process.env};const handlers={};try{process.env.QWEN_WORKFLOW_ROLE='inspect';
 installToolHooks({on:(name,fn)=>handlers[name]=fn});const ctx={model:{provider:'local-qwen-workflow'}};
 for(const name of ['edit','write','bash','workflow_test','plan_store','development_request'])assert.equal((await handlers.tool_call({toolName:name,input:{}},ctx)).block,true);
 assert.equal(await handlers.tool_call({toolName:'source_query',input:{}},ctx),undefined);
 assert.equal((await handlers.tool_call({toolName:'project_map',input:{action:'gate'}},ctx)).block,true);
 }finally{process.env=saved;}
});
