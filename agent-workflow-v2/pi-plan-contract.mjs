/** Direct JSON types are required by Qwen's XML parameter parser. */
import {Type} from '@earendil-works/pi-ai';

export const caseSchema=()=>Type.Object({id:Type.String(),given:Type.String(),when:Type.String(),then:Type.String()},{additionalProperties:false});
export const coverageSchema=()=>Type.Array(Type.Object({criterion:Type.String(),test:Type.Integer({minimum:0})},{additionalProperties:false}));
export const executionSchema=()=>Type.Object({timeout_seconds:Type.Integer({minimum:30,maximum:2700}),
  test_timeout_seconds:Type.Integer({minimum:1,maximum:300}),on_failure:Type.Literal('replan')},{additionalProperties:false});
export function contextSchema(){
  return Type.Object({interfaces:Type.Array(Type.String(),{maxItems:6}),
    symbols:Type.Array(Type.Object({path:Type.String(),name:Type.String()}),{maxItems:8}),
    reference_files:Type.Array(Type.String(),{maxItems:5}),
    architecture_sections:Type.Optional(Type.Array(Type.Object({id:Type.String(),sha256:Type.String()}),{maxItems:5})),
    architecture_update_required:Type.Optional(Type.Boolean()),
    preset:Type.Optional(Type.String({enum:['small','standard','large']})),
    window_tokens:Type.Optional(Type.Integer({enum:[32768,65536,98304,131072]})),
    thinking:Type.Optional(Type.String({enum:['on','off']})),
    reasoning_effort:Type.Optional(Type.String({enum:['low','medium','xhigh']})),
    reasoning_budget_tokens:Type.Optional(Type.Integer({minimum:0,maximum:30720})),
    research_briefs:Type.Optional(Type.Array(Type.String(),{maxItems:2})),
    knowledge_topics:Type.Optional(Type.Array(Type.String(),{maxItems:4})),
    selected_symbols_only:Type.Optional(Type.Boolean()),
    fixture_test_patterns:Type.Optional(Type.Array(Type.String(),{maxItems:8})),
    estimate:Type.Object(Object.fromEntries(['framework','shadow','source','tests','history'].map(k=>[k,Type.Integer({minimum:k==='framework'?6144:0})])),{additionalProperties:false}),
    margin_tokens:Type.Integer({minimum:1024}),max_input_tokens:Type.Integer({minimum:512,maximum:57344}),
    max_output_tokens:Type.Integer({minimum:512,maximum:32768})},{additionalProperties:false});
}
export function childParameters(){
  return Type.Object({id:Type.String({minLength:1}),goal:Type.String({minLength:1}),
    steps:Type.Array(Type.String({minLength:1}),{minItems:2,maxItems:6}),assumptions:Type.Array(Type.String()),
    test_strategy:Type.String({minLength:1}),estimated_changed_lines:Type.Integer({minimum:1,maximum:300}),
    files:Type.Array(Type.String(),{minItems:1,maxItems:8}),tests:Type.Array(Type.Array(Type.String(),{minItems:1}),{minItems:1}),
    acceptance:Type.Array(caseSchema(),{minItems:1}),coverage:coverageSchema(),context:contextSchema(),
    execution:executionSchema(),depends_on:Type.Array(Type.String()),inspect:Type.Optional(Type.Array(Type.String()))},
    {additionalProperties:false});
}
