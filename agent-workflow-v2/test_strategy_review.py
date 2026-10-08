"""Strategy repair rejects circular retries while retaining frozen acceptance."""
import copy
import unittest
from strategy_review import POLICY, validate
import test_replan_patch as patch_tests


def report(criterion='T1-main'):
    """Use a generic normalization observation, never production-task repair advice."""
    return {'expectation_checks': [{'criterion': criterion, 'status': 'unknown',
                'evidence': 'The captured assertion lacks its setup; no causal conclusion is established.'}],
            'abandoned_assumptions': ['The previous diagnosis assumed the test setup was correct.'],
            'strategy_change': 'Inspect the boundary fixture and measure the current output before selecting an edit.',
            'first_check': 'Run the declared boundary test and record its input plus actual output before editing.',
            'stop_condition': 'Stop if the observation contradicts this diagnosis or requires another file scope.'}


class StrategyValidationTests(unittest.TestCase):
    def setUp(self):
        self.packet = {'strategy_review_policy': dict(POLICY), 'failed_todo': {
            'acceptance': [{'id': 'A'}], 'steps': ['Assume the parser is wrong', 'Rewrite it']}}
        review = report('A')
        self.fields = {'strategy_review': review, 'steps': [review['first_check'], 'Repair the measured mismatch']}

    def test_valid_report_is_copied_and_unknown_does_not_require_an_invented_diagnosis(self):
        self.fields['strategy_review']['abandoned_assumptions'] = []
        original = copy.deepcopy(self.fields)
        result = validate(self.packet, self.fields)
        result['expectation_checks'][0]['evidence'] = 'changed'
        self.assertEqual(self.fields, original)

    def test_new_reviews_require_report_but_historical_pinned_packets_remain_valid(self):
        with self.assertRaisesRegex(ValueError, 'strategy_review requires'):validate(self.packet, {})
        historical = {'failed_todo': self.packet['failed_todo']}
        self.assertIsNone(validate(historical, {}))
        self.assertEqual(validate(historical, self.fields), self.fields['strategy_review'])

    def test_unchanged_budget_only_and_mismatched_first_steps_are_rejected(self):
        for steps in (None, [], self.packet['failed_todo']['steps'], ['Different observation', 'Run tests']):
            fields = {**self.fields, 'steps': steps, 'context_overlay': {'max_input_tokens': 32768}}
            with self.subTest(steps=steps), self.assertRaisesRegex(ValueError, 'changed steps'):
                validate(self.packet, fields)

    def test_malformed_reports_and_wrong_criterion_do_not_pass_python_boundary(self):
        bad = [None, [], {}, {'unexpected': True}]
        for key, values in {
            'expectation_checks': [[], 'text', [{}], [{'criterion': 'B', 'status': 'unknown', 'evidence': 'x'*30}],
                [{'criterion': [], 'status': 'unknown', 'evidence': 'x'*30}],
                [{'criterion': 'A', 'status': [], 'evidence': 'x'*30}],
                [{'criterion': 'A', 'status': 'guess', 'evidence': 'x'*30}],
                [{'criterion': 'A', 'status': 'unknown', 'evidence': 1}]],
            'abandoned_assumptions': ['text', ['short'], ['valid assumption']*9],
            'strategy_change': ['', 'x'*1801], 'first_check': [None], 'stop_condition': [123]
        }.items():
            bad += [{**report('A'), key: value} for value in values]
        duplicate = report('A');duplicate['expectation_checks'] *= 2;bad.append(duplicate)
        oversized = report('A');oversized['abandoned_assumptions'] = ['λ'*1000]*8;bad.append(oversized)
        for value in bad:
            with self.subTest(value=str(value)[:80]), self.assertRaises(ValueError):
                validate(self.packet, {**self.fields, 'strategy_review': value})

    def test_contract_conflict_cannot_publish_a_corrective_plan(self):
        self.fields['strategy_review']['expectation_checks'][0]['status'] = 'contract_conflict'
        with self.assertRaisesRegex(ValueError, 'user-directed replanning'):validate(self.packet, self.fields)


class StrategyPersistenceTests(unittest.TestCase):
    setUp = patch_tests.RecoveryPatchTests.setUp
    save = patch_tests.RecoveryPatchTests.save
    def test_strategy_report_reaches_selected_executor_task_without_changing_other_contracts(self):
        self.packet['strategy_review_policy'] = dict(POLICY)
        review = report(self.packet['failed_todo']['acceptance'][0]['id'])
        result = self.save({**self.fields, 'strategy_review': review,
                            'steps': [review['first_check'], 'Repair only the observed mismatch and run all frozen checks.']})
        self.assertEqual(result['tasks'][0]['repair_strategy_review'], review)
        self.assertEqual(result['tasks'][1], self.plan['tasks'][1])
        for key in ('acceptance', 'tests', 'files', 'coverage'):
            self.assertEqual(result['tasks'][0][key], self.plan['tasks'][0][key])

    def test_rejected_strategy_does_not_write_output_or_mutate_original(self):
        self.packet['strategy_review_policy'] = dict(POLICY)
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'strategy_review requires'):self.save()
        self.assertFalse(self.output.exists());self.assertEqual(self.path.read_bytes(), original)

    def test_prior_strategy_report_is_revisable_in_next_review(self):
        from replan_brief import separate_strategy
        task = {**self.packet['failed_todo'], 'repair_strategy_review': report()}
        contract, strategy = separate_strategy(task)
        self.assertNotIn('repair_strategy_review', contract)
        self.assertEqual(strategy['repair_strategy_review'], task['repair_strategy_review'])


if __name__ == '__main__':unittest.main()
