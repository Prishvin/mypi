/** Actual Pi system prompt selects review instructions without new-plan commands. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {installPromptHooks} from './pi-hooks.mjs';

test('draft, refinement and coverage use compatible system instructions for local and cloud planners',async()=>{
  const runtime=mkdtempSync(join(tmpdir(),'planning-mode-'));
  const keys=['QWEN_WORKFLOW_RUNTIME','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_SESSION',
    'QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_PLAN_DRAFT','QWEN_WORKFLOW_PLAN_COVERAGE',
    'QWEN_WORKFLOW_PLANNER','QWEN_WORKFLOW_SKILLS'];
  const previous=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  try{
    for(const key of keys)delete process.env[key];
    Object.assign(process.env,{QWEN_WORKFLOW_RUNTIME:runtime,QWEN_WORKFLOW_PROJECT:runtime,
      QWEN_WORKFLOW_SESSION:runtime,QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLANNER:'chatgpt'});
    for(const file of ['qwen-rules.txt','architect-rules.txt','architect-review-rules.txt'])
      writeFileSync(join(runtime,file),readFileSync(new URL(file,import.meta.url)));
    const hooks={};installPromptHooks({on:(event,fn)=>{hooks[event]=fn;}},fileURLToPath(new URL('.',import.meta.url)));
    const prompt=async provider=>(await hooks.before_agent_start({systemPrompt:'Base instructions'},
      {model:{provider}})).systemPrompt;
    for(const provider of ['local-qwen-workflow','openai']){
      delete process.env.QWEN_WORKFLOW_PLAN_DRAFT;delete process.env.QWEN_WORKFLOW_PLAN_COVERAGE;
      assert.match(await prompt(provider),/Save a JSON object with exactly these required top-level field names/);
      for(const coverage of [false,true]){
        process.env.QWEN_WORKFLOW_PLAN_DRAFT=join(runtime,'bound.json');
        if(coverage)process.env.QWEN_WORKFLOW_PLAN_COVERAGE='1';
        const text=await prompt(provider);
        assert.match(text,/ARCHITECT REVIEW MODE/);
        assert.match(text,/context_overlay/);
        assert.doesNotMatch(text,/Save a JSON object with exactly these required top-level field names/);
        assert.doesNotMatch(text,/Finish by calling plan_store with the architecture and ordered todos/);
      }
    }
    assert.equal(await hooks.before_agent_start({systemPrompt:'Base'},{model:{provider:'unrelated'}}),undefined);
  }finally{
    for(const key of keys)if(previous[key]===undefined)delete process.env[key];else process.env[key]=previous[key];
    rmSync(runtime,{recursive:true,force:true});
  }
});
