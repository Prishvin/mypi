/** Planner/reviewer request caps must not masquerade as future executor contracts. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtempSync,rmSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {sessionLimits} from './pi-session-limits.mjs';
import {installPromptHooks} from './pi-hooks.mjs';

const caps={QWEN_WORKFLOW_INPUT_BUDGET:'57344',QWEN_WORKFLOW_OUTPUT_BUDGET:'16384',
 QWEN_WORKFLOW_THINKING:'on',QWEN_WORKFLOW_REASONING:'medium',QWEN_WORKFLOW_REASONING_BUDGET_TOKENS:'1024'};

test('planning controls distinguish the current response from independently budgeted future work',()=>{
 for(const role of ['architect','reviewer']){
  const text=sessionLimits(role,caps);
  assert.match(text,/this model call only/);assert.match(text,/output=16384/);
  assert.match(text,/thinking cap=1024/);assert.match(text,/reasoning effort=medium/);
  assert.match(text,/Do not copy or clamp future task budgets/);
  assert.match(text,/future task may validly use more output or thinking tokens/);
  assert.doesNotMatch(text,/Effective task caps|Follow the selected frozen contract/);
 }
});

test('executor limits retain frozen-contract semantics while other phases do not inherit them',()=>{
 assert.match(sessionLimits('code',caps),/selected frozen todo and explicit launch overrides/);
 for(const role of ['chat','inspect','intake','research','memory']){
  const text=sessionLimits(role,caps);
  assert.doesNotMatch(text,/frozen todo/);assert.match(text,/only to this conversation phase/);
 }
 assert.match(sessionLimits('reviewer',{...caps,QWEN_WORKFLOW_REASONING_BUDGET_TOKENS:undefined}),/thinking cap=none\/native/);
});

test('actual local and cloud system prompts keep planning and execution budget scopes separate',async()=>{
 const root=mkdtempSync(join(tmpdir(),'session-limits-'));
 const values={...caps,QWEN_WORKFLOW_RUNTIME:root,QWEN_WORKFLOW_PROJECT:root,QWEN_WORKFLOW_SESSION:root,
  QWEN_WORKFLOW_PLANNER:'chatgpt',QWEN_WORKFLOW_EXECUTOR:'chatgpt',QWEN_WORKFLOW_ROLE:'architect',
  QWEN_WORKFLOW_PLAN_DRAFT:undefined,QWEN_WORKFLOW_SKILLS:undefined,QWEN_WORKFLOW_STATE:undefined};
 const prior=Object.fromEntries(Object.keys(values).map(k=>[k,process.env[k]]));
 try{
  for(const [key,value] of Object.entries(values))if(value===undefined)delete process.env[key];else process.env[key]=value;
  for(const name of ['architect-rules.txt','architect-review-rules.txt','reviewer-rules.txt','qwen-rules.txt'])
   writeFileSync(join(root,name),readFileSync(new URL(name,import.meta.url)));
  const hooks={};installPromptHooks({on:(event,fn)=>{hooks[event]=fn;}},root);
  for(const provider of ['local-qwen-workflow','openai'])for(const role of ['architect','reviewer','code']){
   process.env.QWEN_WORKFLOW_ROLE=role;
   for(const bound of role==='architect'?[false,true]:[false]){
    if(bound)process.env.QWEN_WORKFLOW_PLAN_DRAFT=join(root,'bound.json');else delete process.env.QWEN_WORKFLOW_PLAN_DRAFT;
    const result=await hooks.before_agent_start({systemPrompt:'Base'},{model:{provider}});
    assert.match(result.systemPrompt,new RegExp('CURRENT '+role.toUpperCase()+' SESSION LIMITS'));
    assert.doesNotMatch(result.systemPrompt,/Effective task caps/);
    if(role==='code')assert.match(result.systemPrompt,/selected frozen todo and explicit launch overrides/);
    else{
     assert.match(result.systemPrompt,/Do not copy or clamp future task budgets/);
     assert.doesNotMatch(result.systemPrompt,/Follow the selected frozen contract/);
    }
   }
  }
  assert.equal(await hooks.before_agent_start({systemPrompt:'Base'},{model:{provider:'unrelated'}}),undefined);
 }finally{
  for(const [key,value] of Object.entries(prior))if(value===undefined)delete process.env[key];else process.env[key]=value;
  rmSync(root,{recursive:true,force:true});
 }
});
