/** Recovery exposes only typed fields for the failed contract; Python preserves the queue. */
import {Type} from '@earendil-works/pi-ai';
import {repairParameters} from './pi-plan-draft.mjs';

export function recoveryParameters(){
  const fields=repairParameters('failed-task').properties;
  const allowed=['steps','assumptions','test_strategy','estimated_changed_lines','context_overlay',
    'execution','add_tests','add_coverage','add_acceptance','architecture_replacements'];
  return Type.Object({failure_analysis:Type.String({minLength:40,
    description:'Observed failure, cause or uncertainty, smallest corrective approach and validation.'}),
    ...Object.fromEntries(allowed.map(key=>[key,fields[key]]))},{additionalProperties:false});
}
