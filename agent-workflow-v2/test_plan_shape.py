"""Metadata normalization must not replace scope, acceptance or fixture commands."""
import copy
import unittest
from plan_shape import canonical


class PlanShapeTests(unittest.TestCase):
    def test_zero_cap_with_thinking_off_normalizes_without_enabling_thinking(self):
        from plans import validate_context
        from pathlib import Path
        raw={'tasks':[{'context':{'thinking':'off','reasoning_budget_tokens':0,
                                  'max_input_tokens':8192,'max_output_tokens':8192}}]}
        before=copy.deepcopy(raw);result=canonical(raw)
        self.assertEqual(raw,before);self.assertEqual(result['tasks'][0]['context']['thinking'],'off')
        self.assertNotIn('reasoning_budget_tokens',result['tasks'][0]['context'])
        validate_context(Path.cwd(),result['tasks'][0])
        self.assertTrue(result['schema_normalization'])
        raw['tasks'][0]['context']['reasoning_budget_tokens']=512
        with self.assertRaisesRegex(ValueError,'thinking-off'):validate_context(Path.cwd(),canonical(raw)['tasks'][0])
        raw['tasks'][0]['context'].update(thinking='on',reasoning_budget_tokens=0)
        self.assertEqual(canonical(raw)['tasks'][0]['context']['reasoning_budget_tokens'],0)
    def test_aliases_preserve_full_task_contract_and_original_proposal(self):
        todo={'id':'T1','files':['one.py'],'acceptance':[{'id':'A'}],
              'tests':[['node','/exact/frozen.mjs']],'context':{'max_input_tokens':8192}}
        raw={'goal':'Work','architecture_notes':{'module':'one'},'todos':[todo]}
        before=copy.deepcopy(raw);result=canonical(raw)
        self.assertEqual(raw,before);self.assertEqual(result['tasks'],[todo])
        self.assertIn('module',result['architecture']);self.assertEqual(len(result['schema_normalization']),2)
        self.assertNotIn('todos',result);self.assertNotIn('architecture_notes',result)

    def test_conflicts_are_not_silently_chosen(self):
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            canonical({'tasks':[{'id':'A'}],'todos':[{'id':'B'}]})
        with self.assertRaisesRegex(ValueError,'nonempty'):
            canonical({'architecture_notes':{}})

    def test_symbol_pairs_and_coverage_map_preserve_semantic_references(self):
        raw={'tasks':[{'acceptance':[{'id':'A'}],'tests':[['node','/exact/test.mjs']],
              'coverage':{'A':0},'context':{'symbols':[['one.py','pick']],'thinking':True}}]}
        result=canonical(raw)['tasks'][0]
        self.assertEqual(result['coverage'],[{'criterion':'A','test':0}])
        self.assertEqual(result['context']['symbols'],[{'path':'one.py','name':'pick'}])
        self.assertEqual(result['context']['thinking'],'on')
        self.assertEqual(result['acceptance'],raw['tasks'][0]['acceptance'])
        self.assertEqual(result['tests'],raw['tasks'][0]['tests'])
        with self.assertRaisesRegex(ValueError,'integer'):
            canonical({'tasks':[{'coverage':{'A':'0'}}]})

    def test_multiple_coverage_indices_preserve_every_link_and_reject_ambiguity(self):
        from plans import validate_coverage
        raw={'tasks':[{'id':'T1','acceptance':[{'id':'A','given':'x','when':'y','then':'z'}],
            'tests':[['node','/one.mjs'],['node','/two.mjs']],'coverage':{'A':[0,1]}}]}
        before=copy.deepcopy(raw);task=canonical(raw)['tasks'][0]
        self.assertEqual(raw,before)
        self.assertEqual(task['coverage'],[{'criterion':'A','test':0},{'criterion':'A','test':1}])
        self.assertEqual(task['tests'],raw['tasks'][0]['tests'])
        validate_coverage(task)
        for ambiguous in [[],['0'],[True]]:
            with self.assertRaisesRegex(ValueError,'integer'):
                canonical({'tasks':[{'coverage':{'A':ambiguous}}]})
        invalid=canonical({'tasks':[{'id':'T1','acceptance':raw['tasks'][0]['acceptance'],
            'tests':[['node','/one.mjs']],'coverage':{'A':[0,1]}}]})['tasks'][0]
        with self.assertRaisesRegex(ValueError,'invalid'):
            validate_coverage(invalid)

    def test_single_acceptance_object_retains_exact_observation(self):
        criterion={'id':'A','given':'recorded state','when':'actual action','then':'observable result'}
        raw={'tasks':[{'acceptance':criterion,'tests':[['node','/frozen.mjs']]}]}
        before=copy.deepcopy(raw);result=canonical(raw)
        self.assertEqual(raw,before)
        self.assertEqual(result['tasks'][0]['acceptance'],[criterion])
        self.assertEqual(result['tasks'][0]['tests'],raw['tasks'][0]['tests'])
        ambiguous={'A':criterion}
        self.assertEqual(canonical({'tasks':[{'acceptance':ambiguous}]})['tasks'][0]['acceptance'],ambiguous)


if __name__=='__main__':unittest.main()
