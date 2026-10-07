/** Model-facing refinement uses flat fields; Python supplies the pinned target. */
import {Type} from '@earendil-works/pi-ai';
import {caseSchema,coverageSchema,contextSchema,executionSchema,childParameters} from './pi-plan-contract.mjs';

function changes(){
  return {estimated_changed_lines:Type.Optional(Type.Integer({minimum:1,maximum:300})),
    steps:Type.Optional(Type.Array(Type.String(),{minItems:2,maxItems:6})),
    test_strategy:Type.Optional(Type.String()),assumptions:Type.Optional(Type.Array(Type.String())),
    context_overlay:Type.Optional(Type.Partial(contextSchema(),{additionalProperties:false,description:'Merge changed context fields. Let E=sum(estimate); margin_tokens >= max(1024,ceil(E*0.25)), and E+margin <= max_input_tokens.'})),
    execution:Type.Optional(executionSchema()),
    criterion_replacements:Type.Optional(Type.Array(Type.Object({old:caseSchema(),new:caseSchema(),reason:Type.String({minLength:16})},{additionalProperties:false}))),
    add_files:Type.Optional(Type.Array(Type.String())),add_tests:Type.Optional(Type.Array(Type.Array(Type.String()))),
    add_coverage:Type.Optional(coverageSchema()),add_acceptance:Type.Optional(Type.Array(caseSchema()))};
}
export function repairParameters(target){
  const architecture_replacements=Type.Optional(Type.Array(Type.Object({old:Type.String({minLength:1}),new:Type.String({minLength:1})},{additionalProperties:false})));
  if(target)return Type.Object({...changes(),
    unchanged:Type.Optional(Type.Boolean({description:'True only when the selected task needs no changes; cannot combine with edits.'})),
    child_refs:Type.Optional(Type.Array(Type.String({pattern:'^[a-f0-9]{64}$'}),{minItems:2,maxItems:4,
      description:'For a split ONLY: ordered receipts returned by plan_child_store. Do not combine with direct task changes.'})),
    architecture_replacements},{additionalProperties:false,minProperties:1});
  return Type.Object({task_updates:Type.Array(Type.Object({id:Type.String(),...changes(),
    replace_with:Type.Optional(Type.Array(childParameters(),{minItems:2,maxItems:4}))},{additionalProperties:false}),{minItems:1}),
    architecture_replacements},{additionalProperties:false});
}
