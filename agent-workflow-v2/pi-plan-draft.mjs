/** A compact authoring schema for repairing unaccepted proposals, without a full resend. */
import { Type } from '@earendil-works/pi-ai';

export function repairParameters(target) {
  /** Keep corrections typed; full V3 validation remains native and mandatory. */
  return Type.Object({task_updates:Type.Union([Type.Array(Type.Object({id:target?Type.Literal(target):Type.String(),
    estimated_changed_lines:Type.Optional(Type.Integer({minimum:1,maximum:300})),
    steps:Type.Optional(Type.Array(Type.String(),{minItems:2,maxItems:6})),
    test_strategy:Type.Optional(Type.String()), assumptions:Type.Optional(Type.Array(Type.String())),
    context_overlay:Type.Optional(Type.Any({description:'Merge only changed context fields into this task; use context_overlay, not context.'})), execution:Type.Optional(Type.Any()),
    criterion_replacements:Type.Optional(Type.Array(Type.Object({old:Type.Any(),new:Type.Any(),reason:Type.String({minLength:16})}))),
    add_files:Type.Optional(Type.Array(Type.String())),
    add_tests:Type.Optional(Type.Array(Type.Array(Type.String()))),
    add_coverage:Type.Optional(Type.Array(Type.Object({criterion:Type.String({description:'Exact existing acceptance ID, or an ID added in add_acceptance in this same patch.'}),test:Type.Integer({minimum:0})}),{description:'Append coverage entries while preserving existing coverage; use add_coverage, not coverage.'})),
    add_acceptance:Type.Optional(Type.Array(Type.Object({id:Type.String(),given:Type.String(),when:Type.String(),then:Type.String()}))),
    replace_with:Type.Optional(Type.Array(Type.Any(),{minItems:1}))
  },{additionalProperties:false}),{minItems:1,...(target?{maxItems:1,description:'Exactly one object for '+target+'. Combine all changed fields into that object; splits go inside replace_with.'}:{})}),Type.String({maxLength:1048576,description:'Compatibility for literal JSON serialized by legacy tool adapters; prefer an array of objects.'})]), architecture_replacements:Type.Optional(Type.Array(
    Type.Object({old:Type.String({minLength:1}),new:Type.String({minLength:1})}))) },{additionalProperties:false});
}
