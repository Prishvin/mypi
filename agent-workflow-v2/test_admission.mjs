/** Cloud planning uses its own input limit and serializes tools/history for admission. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {installPromptHooks} from './pi-hooks.mjs';

test('cloud planning admission preserves xhigh and rejects a full-payload overflow',async()=>{
  const old={...process.env},folder=mkdtempSync(join(tmpdir(),'mypi-cloud-budget-'));
  let failure=false,aborted=0,calls=0;
  try {
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLANNER:'chatgpt',
      QWEN_WORKFLOW_SESSION:folder,QWEN_WORKFLOW_INPUT_BUDGET:'196608',QWEN_WORKFLOW_OUTPUT_BUDGET:'32768',
      QWEN_WORKFLOW_REASONING:'xhigh'});
    const hooks={};installPromptHooks({on:(name,fn)=>{hooks[name]=fn;},exec:async(_bin,args)=>{
      calls++;assert.ok(args.includes('196608'));return {code:failure?1:0,stdout:JSON.stringify({passed:!failure}),stderr:''};
    }},folder);
    const payload={input:[{role:'user',content:'Architecture request'}],tools:[{name:'plan_store'}],reasoning:{effort:'xhigh'}};
    const ctx={model:{provider:'openai',id:'gpt-6.1-sol'},abort:()=>aborted++};
    const result=await hooks.before_provider_request({payload},ctx);
    assert.equal(result.max_output_tokens,32768);assert.equal(result.reasoning.effort,'xhigh');
    assert.deepEqual(JSON.parse(readFileSync(join(folder,'request-budget.json'),'utf8')),result);
    failure=true;await assert.rejects(()=>hooks.before_provider_request({payload},ctx),/Context budget exceeded/);
    assert.equal(aborted,1);assert.equal(calls,2);
  }finally {
    for(const key of Object.keys(process.env))if(!(key in old))delete process.env[key];
    Object.assign(process.env,old);rmSync(folder,{recursive:true,force:true});
  }
});
