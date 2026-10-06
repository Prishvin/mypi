"""Bound native research separately from deep planning without changing cloud settings."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import phase_service


class PhaseBudgetTests(unittest.TestCase):
    """Verify actual launcher argv for isolated model phases with no inference."""
    def command(self, role, backend):
        """Capture the launched command in a disposable evidence directory."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def invoke_stub(command, attempt, timeout):
                attempt.mkdir(parents=True, exist_ok=True)
                return {'exit_code':1}
            with patch('phase_service.invoke', side_effect=invoke_stub) as invoke, \
                 patch('run_metrics.collect', return_value={}):
                result, draft = phase_service.run(root/'project', role, 'request', root/'phase', backend)
            self.assertFalse(result['passed'])
            self.assertIsNone(draft)
            return invoke.call_args.args[0]

    def test_local_research_uses_medium_with_1024_thinking_cap(self):
        command = self.command('research', 'qwen')
        self.assertEqual(command[command.index('--reasoning-budget')+1], '1024')
        self.assertEqual(command[command.index('--reasoning')+1], 'medium')
        self.assertEqual(command[command.index('--output-tokens')+1], '8192')

    def test_memory_keeps_512_cap_and_low_effort(self):
        command = self.command('memory', 'qwen')
        self.assertEqual(command[command.index('--reasoning-budget')+1], '512')
        self.assertEqual(command[command.index('--reasoning')+1], 'low')

    def test_cloud_and_intake_do_not_inherit_research_cap(self):
        for role, backend in [('research','chatgpt'), ('intake','qwen')]:
            with self.subTest(role=role, backend=backend):
                self.assertNotIn('--reasoning-budget', self.command(role, backend))
