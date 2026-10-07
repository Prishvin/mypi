"""Preserve concrete progress and honest test freshness across context compaction."""
import unittest
from task_progress import describe


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.contract = {'task': {'files': ['source.py', 'test_source.py', 'architecture.md'], 'tests': [['test']]},
                         'declared_hashes': {'source.py': 'old', 'test_source.py': None, 'architecture.md': None}}

    def test_missing_tests_are_next_action_not_a_claim_of_failed_behavior(self):
        result = describe(self.contract, {'source.py': 'new'}, 'now')
        self.assertEqual(result['pending_files'], ['test_source.py'])
        self.assertEqual(result['tests_status'], 'not_run')
        self.assertEqual(result['files'][0]['status'], 'modified')
        self.assertIn('Create the missing', result['next_action'])

    def test_fresh_stale_failed_and_zero_test_evidence_are_distinct(self):
        current = {'source.py': 'old', 'test_source.py': 'test'}
        self.contract['evidence'] = {'snapshot': 'now', 'finished_snapshot': 'now',
                                     'results': [{'exit_code': 0, 'tests_collected': 3}]}
        self.assertEqual(describe(self.contract, current, 'now')['tests_status'], 'passed')
        self.assertEqual(describe(self.contract, current, 'changed')['tests_status'], 'stale')
        self.contract['evidence']['results'][0]['exit_code'] = 1
        self.assertEqual(describe(self.contract, current, 'now')['tests_status'], 'failed')
        self.contract['evidence']['results'][0] = {'exit_code': 0, 'tests_collected': 0}
        self.assertEqual(describe(self.contract, current, 'now')['tests_status'], 'failed')

    def test_existing_file_deletion_is_not_misclassified_as_planned_creation(self):
        result = describe(self.contract, {'test_source.py': 'test'}, 'now')
        self.assertEqual(result['pending_files'], [])
        self.assertEqual(result['files'][0]['status'], 'absent')
        self.assertIn('Run workflow_test', result['next_action'])
