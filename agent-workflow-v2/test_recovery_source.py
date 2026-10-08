"""Recovery reads exact current evidence without expanding planner write authority."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from project_map import scan
from recovery_source import read


class RecoverySourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'project'; self.root.mkdir()
        self.session = self.base / 'review'; self.session.mkdir()
        (self.root / 'work.py').write_text('raise RuntimeError("MUST_NOT_EXECUTE")\n\ndef answer():\n    """Return a fixture."""\n    return 42\n')
        (self.root / 'api.py').write_text('LIMIT = 8\n')
        (self.root / 'unrelated.py').write_text('PRIVATE_VALUE = 91\n')
        self.evidence = self.session / 'replan-evidence.json'
        self.packet = {'project': str(self.root), 'current_snapshot': scan(self.root, ['.'])['snapshot'],
                       'failed_todo': {'files': ['work.py'], 'context': {'interfaces': ['api.py']}}}
        self.save_packet()
        (self.session / 'launch.json').write_text(json.dumps({'project': str(self.root),
            'session': str(self.session), 'role': 'architect', 'replan_evidence': str(self.evidence)}))
        env = patch.dict(os.environ, {'QWEN_WORKFLOW_ROLE': 'architect',
            'QWEN_WORKFLOW_SESSION': str(self.session), 'QWEN_WORKFLOW_REPLAN_EVIDENCE': str(self.evidence)})
        env.start(); self.addCleanup(env.stop)

    def save_packet(self):
        self.evidence.write_text(json.dumps(self.packet))

    def args(self, **changes):
        return argparse.Namespace(**{'command': 'read-symbol', 'path': 'work.py',
            'name': 'answer', 'offset': 0, **changes})

    def test_reads_current_symbol_and_interface_without_running_or_mutating_project(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        value = read(self.root, self.args())
        self.assertIn('return 42', value['source']); self.assertTrue(value['readonly'])
        constant = read(self.root, self.args(path='api.py', name='LIMIT'))
        self.assertIn('LIMIT = 8', constant['source'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        audit = (self.session / 'recovery-source-reads.json').read_text()
        self.assertNotIn('return 42', audit)
        self.assertEqual(json.loads(audit)['calls'][1]['paths'], ['api.py'])

    def test_rejects_undeclared_files_directories_and_outside_paths(self):
        outside = self.base / 'outside.py'; outside.write_text('SECRET = 8\n')
        (self.root / 'linked.py').symlink_to(outside)
        self.packet['failed_todo']['context']['interfaces'].append('linked.py')
        self.packet['current_snapshot'] = scan(self.root, ['.'])['snapshot']; self.save_packet()
        for path in ['unrelated.py', '.', '*.py', str(outside), '../outside.py', 'linked.py']:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'declared task'):
                read(self.root, self.args(command='read-file', path=path))
        self.assertFalse((self.session / 'recovery-source-reads.json').exists())

    def test_stale_snapshot_and_wrong_project_are_rejected(self):
        (self.root / 'work.py').write_text('def answer(): return 43\n')
        with self.assertRaisesRegex(ValueError, 'stale'): read(self.root, self.args())
        with self.assertRaisesRegex(ValueError, 'launched architect'): read(self.base, self.args())

    def test_requires_exact_session_binding_and_architect_role(self):
        with patch.dict(os.environ, {'QWEN_WORKFLOW_ROLE': 'code'}):
            with self.assertRaisesRegex(ValueError, 'launched architect'): read(self.root, self.args())
        alternate = self.base / 'other-evidence.json'; alternate.write_bytes(self.evidence.read_bytes())
        with patch.dict(os.environ, {'QWEN_WORKFLOW_REPLAN_EVIDENCE': str(alternate)}):
            with self.assertRaisesRegex(ValueError, 'launched architect'): read(self.root, self.args())

    def test_no_fixture_or_mutation_command_even_with_valid_binding(self):
        for args in [self.args(command='read-file', fixture_request=True), self.args(command='test'), self.args(command='read-fixture')]:
            with self.assertRaisesRegex(ValueError, 'bounded project source'): read(self.root, args)

    def test_call_budget_survives_separate_reads(self):
        for _ in range(6): read(self.root, self.args())
        with self.assertRaisesRegex(ValueError, 'call budget'): read(self.root, self.args())
        self.assertEqual(len(json.loads((self.session / 'recovery-source-reads.json').read_text())['calls']), 6)

    def test_cumulative_bytes_fail_closed_without_recording_rejected_response(self):
        value = 'def large():\n' + ''.join('    value = "' + 'x' * 78 + '"\n' for _ in range(96))
        (self.root / 'work.py').write_text(value)
        self.packet['current_snapshot'] = scan(self.root, ['.'])['snapshot']; self.save_packet()
        first = read(self.root, self.args(name='large'))
        self.assertLess(first['recovery_budget']['bytes_used'], 12000)
        read(self.root, self.args(name='large'))
        with self.assertRaisesRegex(ValueError, 'byte budget'): read(self.root, self.args(name='large'))
        audit = json.loads((self.session / 'recovery-source-reads.json').read_text())
        self.assertEqual(len(audit['calls']), 2)
        self.assertLessEqual(audit['bytes'], 24000)

    def test_batch_validates_all_paths_before_partial_source_is_returned(self):
        with self.assertRaisesRegex(ValueError, 'declared task'):
            read(self.root, self.args(command='read-symbols-across', paths=['work.py', 'unrelated.py'], names=['answer']))
        result = read(self.root, self.args(command='read-symbols-across', paths=['work.py', 'api.py'], names=['answer', 'LIMIT']))
        self.assertEqual({s['path'] for s in result['symbols']}, {'work.py', 'api.py'})

    def test_real_cli_enforces_binding_before_retrieval(self):
        command = [sys.executable, str(Path(__file__).with_name('workflow.py')), '--root', str(self.root),
                   'read-symbol', 'work.py', 'answer']
        p = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)['readonly'])
        env = dict(os.environ); env.pop('QWEN_WORKFLOW_REPLAN_EVIDENCE')
        blocked = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertNotIn('return 42', blocked.stdout)


if __name__ == '__main__': unittest.main()
