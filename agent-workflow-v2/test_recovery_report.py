"""Structured recovery stops are source-bound and cannot become accepted tasks."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from plan_draft import digest
from recovery_report import store, verified
from recovery_protocol import POLICY
import test_replan_patch as patch_tests
from test_recovery_protocol import decision


class ReportTests(unittest.TestCase):
    def setUp(self):
        patch_tests.RecoveryPatchTests.setUp(self)
        self.session = self.base / 'session'; self.session.mkdir()
        self.packet.update(failure_recovery_policy=POLICY, recovery_plan_sha256=digest(self.plan))
        (self.session / 'replan-evidence.json').write_text(json.dumps(self.packet))
        self.launch = {'session': str(self.session), 'project': str(self.root), 'role': 'architect',
            'plan': str(self.output), 'replan_evidence': str(self.session / 'replan-evidence.json')}
        self.launch_path = self.session / 'launch.json'; self.launch_path.write_text(json.dumps(self.launch))

    def test_report_preserves_source_and_plan_and_cannot_be_overwritten(self):
        original = self.path.read_bytes()
        row = store(self.session, decision('needs_user', 'contract_conflict'))
        self.assertEqual(verified(self.session), row)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError): store(self.session, decision('needs_user'))

    def test_stale_source_wrong_role_or_changed_original_plan_blocks_report(self):
        self.launch_path.write_text(json.dumps({**self.launch, 'role': 'code'}))
        with self.assertRaises(ValueError): store(self.session, decision('needs_user'))
        self.launch_path.write_text(json.dumps(self.launch))
        (self.root / 'changed.py').write_text('x=1\n')
        with self.assertRaises(ValueError): store(self.session, decision('needs_user'))
        (self.root / 'changed.py').unlink()
        self.path.write_text(json.dumps({**self.plan, 'goal': 'Changed outside review'}))
        with self.assertRaises(ValueError): store(self.session, decision('needs_user'))
        self.assertIsNone(verified(self.session))

    def test_repair_and_already_published_plan_cannot_use_stop_escape(self):
        with self.assertRaises(ValueError): store(self.session, decision())
        self.output.write_text('{}')
        with self.assertRaises(ValueError): store(self.session, decision('needs_user'))

    def test_tampered_report_and_later_source_changes_are_not_accepted(self):
        row = store(self.session, decision('environment_fix', 'environment'))
        path = self.session / 'recovery-report.json'
        path.write_text(json.dumps({**row, 'evidence_sha256': 'wrong'}))
        self.assertIsNone(verified(self.session))
        path.write_text(json.dumps(row))
        (self.root / 'changed.py').write_text('x=1\n')
        self.assertIsNone(verified(self.session))

    def test_published_stop_terminates_owned_waiting_process_without_success(self):
        value = decision('framework_fix', 'framework')
        child = f'import recovery_report,time; recovery_report.store({str(self.session)!r},{value!r}); time.sleep(30)'
        prepared = {**self.launch, 'progress_seconds': .1, 'timeout_seconds': 10}
        parent = ('import progress,os; p=progress.run(' + repr([sys.executable, '-c', child]) +
                  ',' + repr(str(Path(__file__).parent)) + ',os.environ.copy(),' + repr(prepared) +
                  '); assert p.returncode==20')
        result = subprocess.run([sys.executable, '-c', parent], cwd=Path(__file__).parent,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.session / 'process.json').read_text())
        self.assertEqual(state['status'], 'recovery_stopped')
        self.assertEqual(state['reason'], 'framework_fix')
        self.assertFalse(self.output.exists())


if __name__ == '__main__': unittest.main()
