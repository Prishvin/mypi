"""Focused recovery preserves immutable contracts and uses the real native save path."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import plans
from project_map import scan
from replan_patch import restore
from failure_context import build
from planning_service import attach_lineage
from test_coverage_plan import draft

ANALYSIS = 'Observed assertion failure; update the selected task steps and rerun its frozen acceptance commands.'


class RecoveryPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve(); self.root = self.base / 'project'; self.root.mkdir()
        self.path = self.base / 'plan.json'; plans.save(self.root, ['.'], draft(), self.path)
        self.plan = json.loads(self.path.read_text())
        self.packet = {'project': str(self.root), 'plan': str(self.path), 'goal': self.plan['goal'],
            'current_snapshot': scan(self.root, ['.'])['snapshot'], 'failed_todo': self.plan['tasks'][0],
            'remaining': self.plan['tasks'], 'completed': [], 'metrics': {},
            'reason': 'acceptance_failed', 'failed_tests': [], 'acceptance_fixtures': {}}
        self.evidence = self.base / 'evidence.json'; self.evidence.write_text(json.dumps(self.packet))
        self.output = self.base / 'result.json'
        self.fields = {'failure_analysis': ANALYSIS, 'steps': ['Inspect failure evidence.', 'Repair and run frozen tests.']}

    def save(self, fields=None):
        result = restore(self.root, ['.'], self.packet, fields or self.fields)
        attach_lineage(result, self.packet)
        plans.save(self.root, ['.'], result, self.output)
        return json.loads(self.output.read_text())

    def test_patch_keeps_all_other_contracts_and_does_not_mutate_inputs_or_source(self):
        before = copy.deepcopy(self.packet); fields = copy.deepcopy(self.fields)
        result = self.save()
        self.assertEqual(result['tasks'][1], self.plan['tasks'][1])
        for key in ('acceptance', 'tests', 'coverage', 'files', 'goal', 'id', 'depends_on', 'context'):
            self.assertEqual(result['tasks'][0][key], self.plan['tasks'][0][key])
        self.assertEqual(result['tasks'][0]['steps'], fields['steps'])
        self.assertEqual(result['failure_analysis'], ANALYSIS)
        self.assertEqual(self.packet, before); self.assertEqual(self.fields, fields)
        self.assertEqual(json.loads(self.path.read_text()), self.plan)
        self.assertEqual(scan(self.root, ['.'])['snapshot'], before['current_snapshot'])
        self.assertEqual(result['replan_lineage']['parent_plan'], str(self.path))

    def test_changed_context_is_exact_not_clamped_to_reviewer_caps(self):
        fields = {'failure_analysis': ANALYSIS, 'context_overlay': {
            'max_input_tokens': 40960, 'max_output_tokens': 32768, 'window_tokens': 98304,
            'reasoning_budget_tokens': 8192, 'reasoning_effort': 'xhigh'}}
        result = self.save(fields)
        for key, value in fields['context_overlay'].items():self.assertEqual(result['tasks'][0]['context'][key], value)
        self.assertEqual(result['tasks'][1], self.plan['tasks'][1])

    def test_completed_dependency_is_removed_but_lineage_and_pending_contracts_survive(self):
        self.plan['tasks'][0]['status'] = 'done'; self.path.write_text(json.dumps(self.plan))
        self.packet.update(completed=[self.plan['tasks'][0]], remaining=[self.plan['tasks'][1]], failed_todo=self.plan['tasks'][1])
        result = self.save()
        self.assertEqual([task['id'] for task in result['tasks']], ['T2'])
        self.assertEqual(result['tasks'][0]['depends_on'], [])
        self.assertEqual(result['replan_lineage']['completed'], self.packet['completed'])

    def test_baseline_path_stays_local_and_does_not_invalidate_snapshot_contract(self):
        data = copy.deepcopy(self.plan); data['tasks'][0]['baseline'] = '/local/frozen-task-state.json'
        self.path.write_text(json.dumps(data))
        self.assertEqual(self.save()['tasks'][1], self.plan['tasks'][1])

    def test_bound_plan_hash_rejects_external_metadata_changes(self):
        from plan_draft import digest
        self.packet['recovery_plan_sha256'] = digest(self.plan)
        changed = copy.deepcopy(self.plan); changed['architecture'] = 'Externally changed'
        self.path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'session was bound'):self.save()
        self.assertFalse(self.output.exists())

    def test_unknown_fields_weakening_scope_change_and_other_target_are_rejected(self):
        for fields in ({'tasks': self.plan['tasks']}, {'id': 'T2'}, {'task_updates': [{'id': 'T2'}]},
            {'criterion_replacements': []}, {'files': ['other.py']}, {'add_files': ['other.py']},
            {'acceptance': []}, {'tests': []}, {'replace_with': []}, {'goal': 'Different'}, {'steps': ['one']},
            {'context_overlay': {'max_input_tokens': 999999}}, {'execution': {'timeout_seconds': 999999}}):
            with self.subTest(fields=fields), self.assertRaises((ValueError, KeyError)):
                self.save({'failure_analysis': ANALYSIS, **fields})
            self.assertFalse(self.output.exists())

    def test_stale_source_plan_or_evidence_and_missing_analysis_fail_before_save(self):
        for target, change in [('packet', {'current_snapshot': 'old'}), ('packet', {'project': '/elsewhere'}),
                               ('plan', {'goal': 'Unchanged goal is allowed', 'tasks': []})]:
            original = copy.deepcopy(self.packet)
            if target == 'packet': self.packet.update(change)
            else:self.path.write_text(json.dumps({**self.plan, **change}))
            with self.subTest(change=change), self.assertRaises(ValueError):self.save()
            self.packet = original; self.path.write_text(json.dumps(self.plan))
        for value in ('short', None, 123):
            with self.assertRaises(ValueError): self.save({'failure_analysis': value})
        self.assertFalse(self.output.exists())

    def test_exact_architecture_replacement_and_additive_test_coverage(self):
        case = {'id': 'T1-empty', 'given': 'empty', 'when': 'normalized', 'then': 'empty'}
        result = self.save({**self.fields, 'add_acceptance': [case], 'add_tests': [['python3', '-m', 'unittest']],
            'add_coverage': [{'criterion': 'T1-empty', 'test': 1}],
            'architecture_replacements': [{'old': 'Pure contracts', 'new': 'Pure bounded contracts'}]})
        self.assertEqual(result['architecture'], 'Pure bounded contracts')
        self.assertEqual(result['tasks'][0]['acceptance'][:-1], self.plan['tasks'][0]['acceptance'])
        self.assertEqual(result['tasks'][0]['tests'][0], self.plan['tasks'][0]['tests'][0])

    def test_native_cli_publishes_focused_patch_with_original_gates(self):
        fields = self.base / 'fields.json'; fields.write_text(json.dumps(self.fields))
        env = {**os.environ, 'QWEN_WORKFLOW_ROLE': 'architect', 'QWEN_WORKFLOW_REPLAN_EVIDENCE': str(self.evidence),
               'QWEN_WORKFLOW_SESSION': str(self.base)}
        for key in ('QWEN_WORKFLOW_PLAN_DRAFT', 'QWEN_WORKFLOW_REQUIRE_REFINEMENT', 'QWEN_WORKFLOW_SHADOW'):
            env.pop(key, None)
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('workflow.py')), '--root', str(self.root),
            'save-plan', '--input', str(fields), '--output', str(self.output)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(self.output.read_text()); self.assertEqual(saved['tasks'][1], self.plan['tasks'][1])
        self.assertEqual(saved['failure_analysis'], ANALYSIS); self.assertIn('replan_lineage', saved)

    def test_focused_prompt_omits_unrelated_full_contracts_but_keeps_overview_and_admission(self):
        self.packet['remaining'][1]['steps'] = ['UNRELATED_FULL_CONTRACT_SENTINEL', 'Do tests']
        self.packet['metrics']['admission_estimate'] = {'admission_tokens': 16685, 'limit': 16384}
        prompt, info = build(self.root, self.packet, 'qwen')
        self.assertNotIn('UNRELATED_FULL_CONTRACT_SENTINEL', prompt)
        self.assertIn('failed_contract', prompt); self.assertIn('T2', prompt)
        self.assertIn('16685', prompt); self.assertIn('16384', prompt)
        self.assertLess(info['packet_estimated_tokens'], info['limits']['packet'])


if __name__ == '__main__':unittest.main()
