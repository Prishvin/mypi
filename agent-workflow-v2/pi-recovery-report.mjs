/** A failure reviewer can publish a bounded escalation without fabricating a plan. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {Type} from '@earendil-works/pi-ai';
import {active,recoverySourceEnabled} from './pi-hooks.mjs';

export function decisionParameters(actions=['repair','needs_user','framework_fix','environment_fix']){
 return Type.Object({
  category:Type.String({enum:['implementation','test_assumption','tool_usage','context_budget','deadline','framework','environment','contract_conflict','unknown']}),
  action:Type.String({enum:actions}),
  summary:Type.String({minLength:40,maxLength:1600}),
  evidence:Type.Array(Type.String({minLength:10,maxLength:800}),{minItems:1,maxItems:5}),
  uncertainties:Type.Array(Type.String({minLength:10,maxLength:800}),{maxItems:5}),
  context_action:Type.String({enum:['keep','retrieve_scoped','reduce_packet','increase_within_limits']})
 },{additionalProperties:false});
}

export function registerRecoveryReport(pi,python,runtime){
 if(!recoverySourceEnabled())return;
 pi.registerTool({name:'recovery_report',label:'Recovery decision',
  description:'Save an evidence-backed needs_user, framework_fix or environment_fix decision and stop this recovery. Does not execute commands, edit source, reset retries or accept a task. Use plan_store for a corrective plan.',
  parameters:decisionParameters(['needs_user','framework_fix','environment_fix']),
  async execute(_id,params,signal,_update,ctx){
   if(!active(ctx.model)||!recoverySourceEnabled())throw new Error('Bound failure recovery only');
   const session=process.env.QWEN_WORKFLOW_SESSION,input=join(session,'recovery-report-input.json');
   writeFileSync(input,JSON.stringify(params));
   const result=await pi.exec(python,[join(runtime,'recovery_report.py'),'--session',session,'--input',input],{signal,timeout:30000});
   if(result.code)throw new Error(result.stdout+result.stderr);
   ctx.abort();
   return {content:[{type:'text',text:result.stdout}],details:{recoveryStopped:true,action:params.action}};
  }
 });
}
