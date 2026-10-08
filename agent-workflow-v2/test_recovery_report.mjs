/** Exercise real recovery registration, prompt composition and Python report publication. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,existsSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {validateToolArguments} from '@earendil-works/pi-ai';
import extension from './pi-extension.mjs';
import {installPromptHooks} from './pi-hooks.mjs';
import {planningFinished} from './pi-planning-finish.mjs';

test('failure prompts and structured stop work for either planner without project mutation',async t=>{
 const runtime=fileURLToPath(new URL('.',import.meta.url)),python=join(runtime,'.venv/bin/python');
 const base=realpathSync(mkdtempSync(join(tmpdir(),'mypi-recovery-report-')));
 const root=join(base,'project'),session=join(base,'session'),plan=join(base,'new-plan.json');mkdirSync(root);mkdirSync(session);
 writeFileSync(join(root,'fixture.py'),'VALUE = 42\n');
 const evidence=join(session,'replan-evidence.json');
 const env={QWEN_WORKFLOW_ROLE:'architect',QWEN_WORKFLOW_PROJECT:root,QWEN_WORKFLOW_SESSION:session,
  QWEN_WORKFLOW_REPLAN_EVIDENCE:evidence,QWEN_WORKFLOW_PLAN:plan,QWEN_WORKFLOW_RUNTIME:runtime,
  QWEN_WORKFLOW_PLANNER:'chatgpt',QWEN_WORKFLOW_SKILLS:undefined,QWEN_WORKFLOW_PLAN_DRAFT:undefined};
 const old=Object.fromEntries(Object.keys(env).map(k=>[k,process.env[k]]));
 t.after(()=>{for(const [k,v] of Object.entries(old))if(v===undefined)delete process.env[k];else process.env[k]=v;rmSync(base,{recursive:true,force:true});});
 for(const [k,v] of Object.entries(env))if(v===undefined)delete process.env[k];else process.env[k]=v;
 const script=`import json,sys\nfrom pathlib import Path\nfrom project_map import scan\nfrom plan_draft import digest\nr,s,p=map(Path,sys.argv[1:]);original=s/'original.json';original.write_text('{}');packet={'project':str(r),'plan':str(original),'current_snapshot':scan(r,['.'])['snapshot'],'recovery_plan_sha256':digest({}),'failure_recovery_policy':{'version':1}}\n(s/'replan-evidence.json').write_text(json.dumps(packet))\n(s/'launch.json').write_text(json.dumps({'role':'architect','project':str(r),'session':str(s),'replan_evidence':str(s/'replan-evidence.json'),'plan':str(p)}))`;
 const setup=spawnSync(python,['-c',script,root,session,plan],{cwd:runtime,encoding:'utf8'});assert.equal(setup.status,0,setup.stderr);
 writeFileSync(join(session,'recovery-capabilities.json'),JSON.stringify({tools:['plan_store','recovery_report','source_query'],review_limits:{context:98304,input_budget:57344,output_budget:32768,reasoning_budget_tokens:8192}}));
 const tools={},hooks={};let aborted=0;
 const pi={registerTool:t=>tools[t.name]=t,registerCommand:()=>{},on:()=>{},exec:async(bin,args)=>{
  const r=spawnSync(bin,args,{cwd:runtime,encoding:'utf8'});return {code:r.status,stdout:r.stdout,stderr:r.stderr};}};
 extension(pi);installPromptHooks({on:(name,fn)=>hooks[name]=fn},runtime);
 for(const provider of ['local-qwen-workflow','openai']){
  const prompt=(await hooks.before_agent_start({systemPrompt:'Base'},{model:{provider}})).systemPrompt;
  assert.match(prompt,/FAILURE RECOVERY AGENT/);assert.match(prompt,/RECOVERY CONTEXT PROCEDURE/);
  assert.match(prompt,/GENERATED CAPABILITIES/);assert.match(prompt,/"reasoning_budget_tokens":8192/);
  assert.match(prompt,/Cloud planning\n\+?does not give|Cloud planning\n?does not give|Cloud planning[\s\S]{0,50}does not give/);
 }
 const fields={category:'framework',action:'framework_fix',summary:'The tool validator rejects a documented valid shape; repair the schema before repeating this task.',
  evidence:['Captured validator exception names a missing property that the recorded schema declares optional.'],
  uncertainties:['Whether the pinned tool schema differs from the installed runtime requires maintainer inspection.'],context_action:'keep'};
 const params=validateToolArguments(tools.recovery_report,{name:'recovery_report',arguments:fields});
 assert.throws(()=>validateToolArguments(tools.recovery_report,{name:'recovery_report',arguments:{...fields,action:'repair'}}));
 const result=await tools.recovery_report.execute('id',params,undefined,undefined,{model:{provider:'local-qwen-workflow'},abort:()=>aborted++});
 assert.equal(aborted,1);assert.equal(result.details.action,'framework_fix');assert.equal(result.details.recoveryStopped,true);
 assert.equal(readFileSync(join(root,'fixture.py'),'utf8'),'VALUE = 42\n');assert.equal(existsSync(plan),false);
 assert.deepEqual(JSON.parse(readFileSync(join(session,'recovery-report.json'),'utf8')).decision,fields);
 assert.equal(planningFinished(),true);
 delete process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE;
 assert.equal(planningFinished(),false);
 const ordinary={};extension({...pi,registerTool:t=>ordinary[t.name]=t});assert.equal(ordinary.recovery_report,undefined);
});
