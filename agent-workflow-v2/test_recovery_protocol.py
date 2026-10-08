"""Evidence dispositions, provider inheritance and actual capability inventories."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from recovery_protocol import POLICY, manifest, validate
import test_recovery_runner as runner_tests
import test_replan_patch as patch_tests


def decision(action='repair', category='unknown'):
    return {'category': category, 'action': action,
        'summary': 'Inspect the captured assertion and current fixture before selecting one bounded corrective action.',
        'evidence': ['Recorded test failure: empty-input assertion returned the unexpected value.'],
        'uncertainties': ['The current fixture setup has not yet been verified.'],
        'context_action': 'retrieve_scoped'}


class ProtocolTests(unittest.TestCase):
    def test_new_protocol_requires_decision_and_old_packets_remain_readable(self):
        self.assertIsNone(validate(None, {}))
        with self.assertRaises(ValueError): validate(None, {'failure_recovery_policy': POLICY})
        source = decision(); result = validate(source, {}, 'repair'); result['evidence'].append('changed')
        self.assertEqual(len(source['evidence']), 1)

    def test_unknown_actions_malformed_evidence_and_framework_as_code_repair_are_rejected(self):
        cases = [{'action': 'restart_server'}, {'category': []}, {'context_action': 'load_all'},
                 {'evidence': []}, {'evidence': ['short']}, {'uncertainties': 'unknown'},
                 {'summary': 'short'}, {'extra': 1}]
        cases += [{'category': category} for category in ('framework', 'environment', 'contract_conflict')]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate({**decision(), **change}, {}, 'repair')
        with self.assertRaises(ValueError): validate(decision('needs_user'), {}, 'repair')

    def test_manifest_uses_effective_provider_caps_and_only_bound_source_and_skills(self):
        for cloud, window, thinking in [(False, 98304, 8192), (True, 272000, None)]:
            launch = {'cloud': cloud, 'context': window, 'input_budget': 196608 if cloud else 57344,
                'output_budget': 32768, 'thinking': 'on', 'reasoning': 'xhigh' if cloud else 'medium',
                'reasoning_budget_tokens': thinking, 'timeout_seconds': 1800,
                'runtime': str(Path(__file__).parent)}
            packet = {'failed_todo': {'files': ['normalize.py'], 'context': {'interfaces': ['types.py']}}}
            tools = 'project_map,plan_store,source_query,recovery_report,skill_use'
            result = manifest(launch, packet, tools)
            self.assertEqual(result['provider'], 'chatgpt' if cloud else 'qwen')
            self.assertEqual(result['review_limits']['context'], window)
            self.assertEqual(result['review_limits']['reasoning_budget_tokens'], thinking)
            self.assertEqual(result['tools'], tools.split(','))
            self.assertEqual(result['source_reads']['allowed_files'], ['normalize.py', 'types.py'])
            self.assertEqual(result['source_reads']['max_calls'], 6)
            self.assertNotIn('edit', result['tools'])
            self.assertNotIn('architecture-update', [s['name'] for s in result['skills']])
            self.assertLess(len(json.dumps(result)), 16000)


class DecisionPersistenceTests(unittest.TestCase):
    setUp = patch_tests.RecoveryPatchTests.setUp
    save = patch_tests.RecoveryPatchTests.save

    def test_repair_decision_survives_save_without_changing_other_tasks(self):
        self.packet['failure_recovery_policy'] = POLICY
        result = self.save({**self.fields, 'recovery_decision': decision()})
        self.assertEqual(result['recovery_decision'], decision())
        self.assertEqual(result['tasks'][1], self.plan['tasks'][1])
        self.assertEqual(result['tasks'][0]['acceptance'], self.plan['tasks'][0]['acceptance'])


class ProviderRoutingTests(unittest.TestCase):
    setUp = runner_tests.RecoveryTests.setUp
    packet = runner_tests.RecoveryTests.packet
    runner = runner_tests.RecoveryTests.runner
    reviewer = runner_tests.RecoveryTests.reviewer

    def test_selected_planner_owns_failure_recovery_for_both_providers(self):
        from recovery_runner import execute
        for provider in ('chatgpt', 'qwen'):
            self.codes = [20, 0]; observed = []
            def review(root, evidence, output, selected, timeout):
                observed.append(selected)
                return self.reviewer(root, evidence, output, selected, timeout)
            with patch('role_selection.load', return_value={'planner': provider, 'reviewer': 'qwen'}):
                result = execute(self.root, self.path, self.base / provider,
                                 executor=self.runner, reviewer=review)
            self.assertEqual(result['code'], 0)
            self.assertEqual(observed, [provider])

    def test_report_is_shown_without_executing_a_repair_or_resetting_allowance(self):
        from recovery_runner import execute
        value = decision('framework_fix', 'framework')
        with patch('role_selection.load', return_value={'planner': 'qwen'}):
            result = execute(self.root, self.path, self.folder, executor=self.runner,
                             reviewer=lambda *a: {'passed': False, 'recovery_decision': value})
        self.assertEqual(result['code'], 20)
        self.assertEqual(result['question']['recovery_decision'], value)
        self.assertEqual(len(self.runs), 1)
        state = json.loads((self.folder / 'recovery-state.json').read_text())
        self.assertEqual(state['status'], 'awaiting_user')
        self.assertTrue(state['spent_ids'])


if __name__ == '__main__': unittest.main()
