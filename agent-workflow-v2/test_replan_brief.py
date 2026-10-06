"""Ensure context distillation cannot weaken or mutate recovery contracts."""
import copy
import unittest
from replan_brief import distill


class ReplanBriefTests(unittest.TestCase):
    def test_exact_pending_contracts_and_untouched_original(self):
        task = {'id': 'T2', 'files': ['a.mjs'], 'acceptance': [
            {'id': 'A2', 'given': 'input', 'when': 'run', 'then': 'pass'}],
            'tests': [['node', '/frozen/test.mjs']], 'status': 'failed',
            'context': {'max_input_tokens': 32768}}
        packet = {'failed_todo': task, 'remaining': [task], 'completed': [
            {'id': 'T1', 'files': ['b.mjs'], 'tests': [['node', 'first.mjs']],
             'execution': {'timeout_seconds': 1200}, 'evidence': '/local/gate'}],
            'metrics': {'requests': 2, 'native_requests': [
                {'prompt_tokens': 1500, 'irrelevant_telemetry': 'x' * 2000}]},
            'failed_tests': [{'exit_code': 1, 'observations': ['Error: mouse aim']}],
            'current_snapshot': 'snapshot', 'acceptance_fixtures': {'/frozen': 'sha'},
            'selected_prototypes': 'function aim(delta): rotate view'}
        original = copy.deepcopy(packet)
        brief = distill(packet)
        self.assertEqual(packet, original)
        self.assertEqual(brief['remaining'][0]['acceptance'], task['acceptance'])
        self.assertEqual(brief['remaining'][0]['tests'], task['tests'])
        self.assertEqual(brief['remaining'][0]['context'], task['context'])
        self.assertEqual(brief['failed_tests'], packet['failed_tests'])
        self.assertEqual(brief['acceptance_fixtures'], packet['acceptance_fixtures'])
        self.assertEqual(brief['selected_prototypes'], packet['selected_prototypes'])
        self.assertEqual(brief['metrics']['largest_completed_prompt_tokens'], 1500)
        self.assertNotIn('failed_todo', brief)
        self.assertEqual(brief['failed_todo_id'], 'T2')
        self.assertNotIn('native_requests', brief['metrics'])

    def test_failed_accepted_regression_remains_visible(self):
        failing = {'todo': 'T1', 'exit_code': 1, 'argv': ['node', '/frozen/T1.mjs']}
        packet = {'regression': {'passed': False, 'reason': 'regression_failed',
            'tests': [failing, {'todo': 'T2', 'exit_code': 0}]}}
        self.assertEqual(distill(packet)['regression_failure'], {
            'reason': 'regression_failed', 'tests': [failing]})


if __name__ == '__main__':
    unittest.main()
