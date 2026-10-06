/** Verify opt-in diagnostic controls isolate thinking from sampling changes. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {installPromptHooks} from './pi-hooks.mjs';
import {fileURLToPath} from 'node:url';

test('thinking-off diagnostic can preserve sampling and reject invalid overrides',async()=>{
  const keys=['QWEN_WORKFLOW_SESSION','QWEN_WORKFLOW_PROJECT','QWEN_WORKFLOW_ROLE',
    'QWEN_WORKFLOW_THINKING','QWEN_WORKFLOW_TEMPERATURE','QWEN_WORKFLOW_TOP_P',
    'QWEN_WORKFLOW_INPUT_BUDGET','QWEN_WORKFLOW_REQUEST_LOG','QWEN_WORKFLOW_REASONING_BUDGET_TOKENS','QWEN_WORKFLOW_SEED'];
  const old=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  try{
    Object.assign(process.env,{QWEN_WORKFLOW_SESSION:'/tmp/pi-sampling-test',QWEN_WORKFLOW_PROJECT:'/repo',
      QWEN_WORKFLOW_ROLE:'code',QWEN_WORKFLOW_THINKING:'off'});
    for(const key of ['QWEN_WORKFLOW_INPUT_BUDGET','QWEN_WORKFLOW_REQUEST_LOG',
      'QWEN_WORKFLOW_REASONING_BUDGET_TOKENS','QWEN_WORKFLOW_TEMPERATURE','QWEN_WORKFLOW_TOP_P','QWEN_WORKFLOW_SEED'])delete process.env[key];
    const hooks={};installPromptHooks({on:(name,handler)=>{hooks[name]=handler;}},fileURLToPath(new URL('.',import.meta.url)));
    const event={payload:{messages:[]}},context={model:{provider:'local-qwen-workflow'}};
    let payload=await hooks.before_provider_request(event,context);
    assert.equal(payload.temperature,.7);assert.equal(payload.top_p,.8);
    process.env.QWEN_WORKFLOW_TEMPERATURE='1';process.env.QWEN_WORKFLOW_TOP_P='.95';
    payload=await hooks.before_provider_request(event,context);
    assert.equal(payload.temperature,1);assert.equal(payload.top_p,.95);
    assert.equal(payload.enable_thinking,false);
    assert.equal(payload.seed,undefined);
    process.env.QWEN_WORKFLOW_SEED='1337';
    payload=await hooks.before_provider_request(event,context);assert.equal(payload.seed,1337);
    process.env.QWEN_WORKFLOW_SEED='-1';
    await assert.rejects(()=>hooks.before_provider_request(event,context),/Invalid sampling seed/);
    process.env.QWEN_WORKFLOW_SEED='1337';
    assert.equal(await hooks.before_provider_request(event,{model:{provider:'unrelated'}}),undefined);
    for(const [key,value] of [['QWEN_WORKFLOW_TOP_P','0'],['QWEN_WORKFLOW_TOP_P','1.1'],['QWEN_WORKFLOW_TEMPERATURE','NaN']]){
      process.env.QWEN_WORKFLOW_TEMPERATURE='1';process.env.QWEN_WORKFLOW_TOP_P='.95';process.env[key]=value;
      await assert.rejects(()=>hooks.before_provider_request(event,context),/Invalid sampling override/);
    }
  }finally{
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
  }
});
