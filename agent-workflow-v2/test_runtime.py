"""A task must not mix tool versions after a live workflow update."""
from pathlib import Path
import tempfile
import unittest
from runtime import capture
from launch import configure, tune_context, validate_model_context
import json


class RuntimeTests(unittest.TestCase):
    """Exercise changes to the original tool files after a session starts."""
    def test_later_tool_edits_do_not_change_session_runtime(self):
        """Source and rule updates leave the running session on its pinned version."""
        with tempfile.TemporaryDirectory() as folder:
            base, session = Path(folder) / 'base', Path(folder) / 'session'
            base.mkdir()
            session.mkdir()
            for name in ('workflow.py', 'qwen-rules.txt', 'architect-rules.txt', 'research-rules.txt', 'intake-rules.txt','reviewer-rules.txt','memory-rules.txt'):
                (base / name).write_text('first version')
            (base/'architect-review-rules.txt').write_text('Pinned review rules')
            (base/'architect-recovery-rules.txt').write_text('Pinned recovery rules')
            (base / 'test_unrelated.py').write_text('do not package tests')
            runtime = capture(base, session)
            (base / 'workflow.py').write_text('second version')
            (base / 'qwen-rules.txt').write_text('new rules')
            (base/'architect-review-rules.txt').write_text('Updated review rules')
            (base/'architect-recovery-rules.txt').write_text('Updated recovery rules')
            self.assertEqual((runtime / 'workflow.py').read_text(), 'first version')
            self.assertEqual((runtime / 'qwen-rules.txt').read_text(), 'first version')
            self.assertFalse((runtime / 'test_unrelated.py').exists())
            self.assertEqual((runtime/'architect-review-rules.txt').read_text(),'Pinned review rules')
            self.assertIn('architect-review-rules.txt',json.loads((runtime/'manifest.json').read_text()))
            self.assertEqual((runtime/'architect-recovery-rules.txt').read_text(),'Pinned recovery rules')
            self.assertIn('architect-recovery-rules.txt',json.loads((runtime/'manifest.json').read_text()))

    def test_todo_budget_keeps_real_context_and_response_space(self):
        """Navigation limits trigger compaction without shrinking the real model context."""
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder)
            configure(config, '27b', 32768)
            tune_context(config, 12000, 4096)
            models = json.loads((config / 'models.json').read_text())
            model = models['providers']['local-qwen-workflow']['models'][0]
            settings = json.loads((config / 'settings.json').read_text())
            self.assertEqual(model['contextWindow'], 32768)
            self.assertEqual(model['maxTokens'], 4096)
            # Full provider usage already includes the envelope; retain admission margin.
            self.assertEqual(settings['compaction']['reserveTokens'], 23373)

    def test_64k_context_can_reserve_32k_output(self):
        """The expanded profile preserves real context while limiting input separately."""
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder)
            configure(config, '27b', 65536)
            tune_context(config, 24576, 32768)
            descriptor = json.loads((config / 'models.json').read_text())['providers']['local-qwen-workflow']['models'][0]
            self.assertEqual(descriptor['contextWindow'], 65536)
            self.assertEqual(descriptor['maxTokens'], 32768)
            # A 24576 admission cap permits 19456 full-request raw tokens.
            self.assertEqual(json.loads((config / 'settings.json').read_text())['compaction']['reserveTokens'], 46080)

    def test_model_context_ceilings(self):
        """27B can select 96k while 128k is available only for Flash Next."""
        validate_model_context('27b', 98304)
        validate_model_context('flash', 131072)
        with self.assertRaises(ValueError):
            validate_model_context('27b', 131072)


if __name__ == '__main__':
    unittest.main()
