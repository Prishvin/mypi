/** Stage one model-authored split contract; only plan_store can accept a plan. */
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {childParameters} from './pi-plan-contract.mjs';

export function refinementTarget(){
  const bound=process.env.QWEN_WORKFLOW_PLAN_DRAFT;
  if(!bound||process.env.QWEN_WORKFLOW_PLAN_COVERAGE==='1')return undefined;
  return JSON.parse(readFileSync(bound,'utf8')).refine_task;
}
export function registerPlanChildren(pi,python,cli,scopeArgs,active){
  const target=refinementTarget();
  if(!target)return;
  pi.registerTool({name:'plan_child_store',label:'Stage one split todo',parameters:childParameters(),
    description:'Stage ONE full V3 child of '+target+'. Pass fields directly, not inside task/tasks. Returns an immutable child_ref. This does not accept or execute a plan. Stage 2-4 children, then call plan_store with their child_refs in dependency order; final child keeps '+target+'. Preserve original cases/tests/files across children. Each child depends on original prerequisites and all earlier children.',
    async execute(_id,params,signal,_update,ctx){
      if(!active(ctx.model)||process.env.QWEN_WORKFLOW_ROLE!=='architect')throw Error('Selected-task architect review only');
      const input=join(process.env.QWEN_WORKFLOW_SESSION,'child-input-'+randomUUID()+'.json');
      writeFileSync(input,JSON.stringify(params));
      const result=await pi.exec(python,[cli,...scopeArgs(process.env.QWEN_WORKFLOW_PROJECT),'stage-plan-child','--input',input],{signal,timeout:30000});
      if(result.code)throw Error(result.stdout+result.stderr);
      return {content:[{type:'text',text:result.stdout}],details:{staged:true,planAccepted:false}};
    }});
}
