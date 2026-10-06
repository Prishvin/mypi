/** Both planner providers receive measured policy; other roles keep their context. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {installPromptHooks} from './pi-hooks.mjs';
import {commandFor} from './pi-extension.mjs';

test('large-shadow instructions reach local and subscription planners only', async () => {
  const keys=['QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_PLANNER','QWEN_WORKFLOW_SKILLS','QWEN_WORKFLOW_RUNTIME'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  const session=mkdtempSync(join(tmpdir(),'pi-navigation-'));
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_SESSION:session,QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLANNER:'chatgpt'});
    delete process.env.QWEN_WORKFLOW_SKILLS;delete process.env.QWEN_WORKFLOW_RUNTIME;
    writeFileSync(join(session,'plan-navigation.txt'),'SHADOW SIZE: total=40000; architecture ONLY; select relevant prototypes.');
    const handlers={}; installPromptHooks({on:(name,handler)=>{handlers[name]=handler;}},fileURLToPath(new URL('.',import.meta.url)));
    for(const provider of ['local-qwen-workflow','openai']) {
      const result=await handlers.before_agent_start({systemPrompt:'base'},{model:{provider}});
      assert.match(result.systemPrompt,/SHADOW SIZE: total=40000/);
    }
    process.env.QWEN_WORKFLOW_ROLE='code';
    const code=await handlers.before_agent_start({systemPrompt:'base'},{model:{provider:'local-qwen-workflow'}});
    assert.doesNotMatch(code.systemPrompt,/SHADOW SIZE: total=40000/);
    assert.equal(await handlers.before_agent_start({systemPrompt:'base'},{model:{provider:'openai'}}),undefined);
  } finally {
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
    rmSync(session,{recursive:true,force:true});
  }
});

test('selected locate paths survive the Pi CLI adapter', () => {
  assert.deepEqual(commandFor('locate',['maths.py'],'double'),['locate','double','--paths','maths.py']);
  assert.deepEqual(commandFor('locate',[],'double'),['locate','double']);
});
