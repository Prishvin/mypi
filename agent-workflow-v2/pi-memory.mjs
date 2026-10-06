/** Distillation has exactly one tool; publication remains deterministic. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {Type} from '@earendil-works/pi-ai';
import {active} from './pi-hooks.mjs';

export function registerMemory(pi,python,runtime) {
  pi.registerTool({name:'memory_store',label:'Save distilled memory',
    description:'Save up to six essential project-memory bullets with exact evidence from the selected response. No project edits. Saving ends distillation.',
    parameters:Type.Object({items:Type.Array(Type.Object({text:Type.String({maxLength:500}),
      evidence:Type.String({minLength:1,maxLength:400})}),{maxItems:6}),skipped_reason:Type.Optional(Type.String({maxLength:300}))}),
    async execute(_id,params,signal,_update,ctx) {
      if(!active(ctx.model)||process.env.QWEN_WORKFLOW_ROLE!=='memory')throw new Error('Memory phase only');
      const session=process.env.QWEN_WORKFLOW_SESSION,output=process.env.QWEN_WORKFLOW_PHASE_OUTPUT;
      const request=join(session,'memory-store.json');writeFileSync(request,JSON.stringify(params));
      const result=await pi.exec(python,[join(runtime,'memory_draft.py'),
        '--packet',process.env.QWEN_WORKFLOW_MEMORY_PACKET,'--request',request,'--output',output],{signal,timeout:30000});
      if(result.code)throw new Error((result.stdout+result.stderr).slice(0,4000));
      return {content:[{type:'text',text:result.stdout}],details:{phase:'memory',output}};
    }});
}
