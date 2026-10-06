/** Review output is validated against run evidence and its separate follow-up plan. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {Type} from '@earendil-works/pi-ai';
import {active} from './pi-hooks.mjs';

export function registerReview(pi,python,runtime) {
  pi.registerTool({name:'review_store',label:'Save final review',
    description:'Save clean or followup review. Each finding needs exact packet evidence IDs and follow-up task IDs. For followup, first save a V3 plan with plan_store. Saving review ends the phase.',
    parameters:Type.Object({verdict:Type.Union(['clean','followup'].map(x=>Type.Literal(x))),summary:Type.String(),
      findings:Type.Array(Type.Object({kind:Type.Union(['unit-test-gap','e2e-test-gap','integration-test-gap','observed-bug','risk'].map(x=>Type.Literal(x))),
        observation:Type.String(),evidence:Type.Array(Type.String()),tasks:Type.Array(Type.String())}),{maxItems:8})}),
    async execute(_id,params,signal,_update,ctx) {
      if(!active(ctx.model)||process.env.QWEN_WORKFLOW_ROLE!=='reviewer')throw new Error('Final reviewer only');
      const request=join(process.env.QWEN_WORKFLOW_SESSION,'review-store.json');writeFileSync(request,JSON.stringify(params));
      const output=process.env.QWEN_WORKFLOW_PHASE_OUTPUT;
      const result=await pi.exec(python,[join(runtime,'review_store.py'),'--request',request,
        '--packet',process.env.QWEN_WORKFLOW_REVIEW_PACKET,'--plan',process.env.QWEN_WORKFLOW_PLAN,'--output',output],{signal,timeout:30000});
      if(result.code)throw new Error((result.stdout+result.stderr).slice(0,4000));
      return {content:[{type:'text',text:result.stdout}],details:{phase:'reviewer',output}};
    }});
}
