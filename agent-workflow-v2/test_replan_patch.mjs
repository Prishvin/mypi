/** Real Pi validation and prompt hooks must advertise one compact recovery patch. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {validateToolArguments} from '@earendil-works/pi-ai';
import {recoveryParameters} from './pi-replan-patch.mjs';
import extension from './pi-extension.mjs';
import {installPromptHooks} from './pi-hooks.mjs';
import {fileURLToPath} from 'node:url';
const analysis='Observed failure evidence; adjust the bounded input budget and rerun frozen acceptance tests.';

test('recovery schema permits typed flat changes and rejects full plans, IDs and weakening',()=>{
 const tool={name:'plan_store',parameters:recoveryParameters()};
 const validate=fields=>validateToolArguments(tool,{name:'plan_store',arguments:fields});
 for(const field of Object.values(tool.parameters.properties)){
  assert.ok(['array','object','integer','string'].includes(field.type));assert.equal(field.anyOf,undefined);
 }
 const fields={failure_analysis:analysis,steps:['Read measured failure','Run frozen tests'],
  context_overlay:{max_input_tokens:24576,window_tokens:65536},add_coverage:[{criterion:'A',test:0}]};
 assert.deepEqual(validate(fields),fields);
 for(const extra of [{tasks:[]},{id:'another'},{task_updates:[]},{criterion_replacements:[]},
  {files:[]},{tests:[]},{add_files:['other']},{child_refs:[]},{context_overlay:'{"max_input_tokens":24576}'}])
  assert.throws(()=>validate({failure_analysis:analysis,...extra}));
 assert.throws(()=>validate({failure_analysis:'short'}));
 assert.throws(()=>validate({failure_analysis:analysis,context_overlay:{estimate:{framework:2048,shadow:512,source:1024,tests:512,history:1024}}}));
 assert.equal(tool.parameters.properties.context_overlay.properties.estimate.properties.framework.minimum,6144);
});

test('actual extension chooses compact recovery schema and system rules for local and cloud',async()=>{
 const values={QWEN_WORKFLOW_REPLAN_EVIDENCE:'/bound/evidence.json',QWEN_WORKFLOW_ROLE:'architect',
  QWEN_WORKFLOW_PLAN_DRAFT:undefined,QWEN_WORKFLOW_PLAN_COVERAGE:undefined,
  QWEN_WORKFLOW_RUNTIME:fileURLToPath(new URL('.',import.meta.url)),QWEN_WORKFLOW_PLANNER:'chatgpt',
  QWEN_WORKFLOW_EXECUTOR:'chatgpt',QWEN_WORKFLOW_SESSION:undefined,QWEN_WORKFLOW_SKILLS:undefined};
 const before=Object.fromEntries(Object.keys(values).map(key=>[key,process.env[key]]));
 try{
  for(const [key,value] of Object.entries(values))if(value===undefined)delete process.env[key];else process.env[key]=value;
  const tools={},hooks={};extension({registerTool:t=>{tools[t.name]=t;},registerCommand:()=>{},on:()=>{}});
  assert.equal(tools.plan_store.parameters.properties.tasks,undefined);
  assert.deepEqual(tools.plan_store.parameters.required,['failure_analysis']);
  assert.match(tools.plan_store.description,/failed todo/);
  installPromptHooks({on:(name,hook)=>{hooks[name]=hook;}},values.QWEN_WORKFLOW_RUNTIME);
  for(const provider of ['local-qwen-workflow','openai']){
   const response=await hooks.before_agent_start({systemPrompt:'Base'},{model:{provider}});
   assert.match(response.systemPrompt,/FOCUSED FAILURE REVIEW/);
   assert.doesNotMatch(response.systemPrompt,/Save a JSON object with exactly these required/);
  }
 }finally{for(const [key,value] of Object.entries(before))if(value===undefined)delete process.env[key];else process.env[key]=value;}
});
