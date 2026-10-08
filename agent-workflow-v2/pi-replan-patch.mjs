/** Recovery exposes only typed fields for the failed contract; Python preserves the queue. */
import {Type} from '@earendil-works/pi-ai';
import {repairParameters} from './pi-plan-draft.mjs';
import {decisionParameters} from './pi-recovery-report.mjs';

export function recoveryParameters(){
  const fields=repairParameters('failed-task').properties;
  const allowed=['steps','assumptions','test_strategy','estimated_changed_lines','context_overlay',
    'execution','add_tests','add_coverage','add_acceptance','architecture_replacements'];
  return Type.Object({...Object.fromEntries(allowed.map(key=>[key,fields[key]])),
    recovery_decision:decisionParameters(['repair']),
    failure_analysis:Type.String({minLength:40,
    description:'Observed failure, cause or uncertainty, smallest corrective approach and validation.'}),
    strategy_review:Type.Object({
      expectation_checks:Type.Array(Type.Object({
        criterion:Type.String({description:'Exact affected frozen acceptance ID.'}),
        status:Type.String({enum:['supported','implementation_gap','test_assumption','unknown','contract_conflict']}),
        evidence:Type.String({minLength:20,maxLength:1800,description:'Observed test/source evidence with names; distinguish unknowns.'})
      },{additionalProperties:false}),{minItems:1,maxItems:16}),
      abandoned_assumptions:Type.Array(Type.String({minLength:10,maxLength:1000}),{maxItems:8,
        description:'Discard unsupported prior restrictions; empty if none are established.'}),
      strategy_change:Type.String({minLength:20,maxLength:1800}),
      first_check:Type.String({minLength:20,maxLength:1800,description:'Small executable observation before speculative edits; copy exactly as steps[0].'}),
      stop_condition:Type.String({minLength:20,maxLength:1800,description:'Evidence that falsifies this strategy and requires stopping/replanning.'})
    },{additionalProperties:false}),
    steps:Type.Array(Type.String({minLength:1}),{minItems:2,
      description:'Changed granular strategy beginning with the exact first_check; preserve frozen acceptance.'})
  },{additionalProperties:false});
}
