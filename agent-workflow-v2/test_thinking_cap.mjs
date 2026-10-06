import test from 'node:test';
import assert from 'node:assert/strict';
import {requireThinkingCaps,registerThinkingCap} from './pi-thinking-cap.mjs';

test('unknown backend cannot silently ignore the cap',async()=>{
  await assert.rejects(()=>requireThinkingCaps(async()=>({ok:false})),/cannot verify/);
  await requireThinkingCaps(async()=>({ok:true,json:async()=>({version:1,thinking_cap:'request-local',field:'pi_thinking_cap'})}));
});

test('slash cap persists defaults but protects frozen worker contracts',async()=>{
  const prior={...process.env};let command,calls=0,notice='';
  Object.assign(process.env,{QWEN_WORKFLOW_PROJECT:'/project',QWEN_WORKFLOW_TOOLKIT:'/toolkit',
    QWEN_WORKFLOW_OUTPUT_BUDGET:'16384',QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLANNER:'local'});
  delete process.env.QWEN_WORKFLOW_STATE;
  const ctx={model:{provider:'local-qwen-workflow'},waitForIdle:async()=>{},ui:{notify:v=>{notice=v;}}};
  const pi={registerCommand:(name,value)=>{assert.equal(name,'thinkingcap');command=value;},
    exec:async()=>{calls++;return {code:0,stdout:'{"thinking_cap":8192}'};}};
  try {
    registerThinkingCap(pi,'python');await command.handler('8192',ctx);
    assert.equal(process.env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS,'8192');assert.equal(calls,1);
    process.env.QWEN_WORKFLOW_STATE='/frozen';await command.handler('4096',ctx);
    assert.match(notice,/frozen contract/);assert.equal(calls,1);
    delete process.env.QWEN_WORKFLOW_STATE;await command.handler('NaN',ctx);
    assert.equal(calls,1);
  }finally{for(const key of Object.keys(process.env))if(!(key in prior))delete process.env[key];Object.assign(process.env,prior);}
});
