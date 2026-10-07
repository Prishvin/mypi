/** The private planner hands off after a successful save, never after an error. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtempSync,writeFileSync,readFileSync,existsSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {installRefreshHooks} from './pi-hooks.mjs';

test('only the selected architect stops on a successful persisted plan',async()=>{
  const keys=['QWEN_WORKFLOW_ROLE','QWEN_WORKFLOW_PLAN','QWEN_WORKFLOW_SESSION'];
  const old=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  const dir=mkdtempSync(join(tmpdir(),'pi-plan-stop-'));
  try{
    const plan=join(dir,'plan.json');writeFileSync(plan,'{"plan_version":3}');
    Object.assign(process.env,{QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PLAN:plan,QWEN_WORKFLOW_SESSION:dir});
    const handlers={};let stopped=0;
    installRefreshHooks({on:(name,fn)=>{handlers[name]=fn;}},'python','workflow.py',()=>[]);
    const event={toolName:'plan_store',content:[],details:{plan}};
    const ctx={model:{provider:'local-qwen-workflow'},abort:()=>{stopped++;}};
    assert.equal((await handlers.tool_result({...event,isError:true},ctx)).isError,true);
    assert.equal(stopped,0);
    assert.equal(await handlers.tool_result(event,{...ctx,model:{provider:'unrelated'}}),undefined);
    assert.equal(existsSync(join(dir,'planning-stop.json')),false);
    assert.equal((await handlers.tool_result(event,ctx)).details.acceptedPlanningStop,true);
    assert.equal(stopped,1);
    const marker=JSON.parse(readFileSync(join(dir,'planning-stop.json'),'utf8'));
    assert.equal(marker.plan,plan);assert.equal(marker.sha256.length,64);
    process.env.QWEN_WORKFLOW_ROLE='code';
    assert.equal(await handlers.tool_result(event,ctx),undefined);assert.equal(stopped,1);
  }finally{
    for(const key of keys)if(old[key]===undefined)delete process.env[key];else process.env[key]=old[key];
    rmSync(dir,{recursive:true,force:true});
  }
});
