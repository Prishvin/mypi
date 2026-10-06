/** Save validated phase outputs; Python retains control of questions and publication. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {Type} from '@earendil-works/pi-ai';
import {active} from './pi-hooks.mjs';

export function registerPhases(pi, python, runtime) {
  const finding=Type.Object({artifact_id:Type.String(),claim:Type.String({maxLength:300}),
    evidence:Type.String({maxLength:400}),confidence:Type.Union(['high','medium','low'].map(x=>Type.Literal(x)))});
  const schemas={research:Type.Object({topics:Type.Array(Type.Object({keyword:Type.String(),why:Type.String(),
    findings:Type.Array(finding,{minItems:1,maxItems:3}),
    implementation_artifacts:Type.Optional(Type.Array(Type.String(),{maxItems:2}))}),{maxItems:4}),
    skipped_reason:Type.Optional(Type.String())}),
    intake:Type.Object({mode:Type.Union(['ask','ready','blocked'].map(x=>Type.Literal(x))),
      question:Type.Optional(Type.Object({text:Type.String(),options:Type.Optional(Type.Array(Type.String(),{maxItems:4}))})),
      refined_prompt:Type.Optional(Type.String()), assumptions:Type.Array(Type.String(),{maxItems:8}),
      unresolved:Type.Array(Type.String(),{maxItems:8})})};
  for (const [role,parameters] of Object.entries(schemas)) {
    pi.registerTool({name:role==='intake'?'intake_store':'knowledge_store',label:'Save '+role+' decision',
      description:role==='intake'?'Save one ambiguity decision (ask, ready or blocked). Maximum two clarification rounds; saving ends this phase.':'Save at most four short researched topics with exact evidence from fetched artifacts. No implementation access. Saving ends this phase.',parameters,
      async execute(_id,params,signal,_update,ctx) {
        if (!active(ctx.model)||process.env.QWEN_WORKFLOW_ROLE!==role) throw new Error('Wrong workflow phase');
        const session=process.env.QWEN_WORKFLOW_SESSION;
        const output=process.env.QWEN_WORKFLOW_PHASE_OUTPUT;
        if (!output) throw new Error('Phase output missing');
        const request=join(session,role+'-store.json');
        writeFileSync(request,JSON.stringify(params));
        const argv=[join(runtime,role==='intake'?'intake.py':'knowledge.py'),'--request',request,'--output',output];
        if (role==='research') argv.push('--session',session);
        else {
          const prompt=JSON.parse(process.env.QWEN_WORKFLOW_INTAKE_PACKET || '{}');
          argv.push('--rounds',String(prompt.answered_rounds??0));
        }
        const result=await pi.exec(python,argv,{signal,timeout:30000});
        if (result.code) throw new Error((result.stdout+result.stderr).slice(0,4000));
        return {content:[{type:'text',text:result.stdout}],details:{phase:role,output}};
      }});
  }
}
