"""Runner output is readable in bounded pages without opening arbitrary session files."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrieval import read_page


class EvidenceLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root, self.session = self.base / 'project', self.base / 'session'
        self.root.mkdir(); self.session.mkdir()
        self.state = self.session / 'task-state.json'
        self.log = self.session / 'task-state-test-0.log'
        self.log.write_text('DIAGNOSTIC measured value: 7\n' + 'ok\n' * 145)
        self.bind()
        env = patch.dict(os.environ, {'QWEN_WORKFLOW_SESSION': str(self.session),
                                      'QWEN_WORKFLOW_STATE': str(self.state)})
        env.start(); self.addCleanup(env.stop)

    def bind(self, root=None, log=None):
        self.state.write_text(json.dumps({'before': {'root': str(root or self.root)},
                                         'evidence': {'results': [{'log': str(log or self.log)}]}}))

    def test_diagnostic_pages_are_readonly_bounded_and_fresh(self):
        before = (self.log.read_bytes(), self.log.stat().st_mtime_ns)
        page = read_page(self.root, str(self.log))
        self.assertEqual(page['mode'], 'test-log'); self.assertTrue(page['readonly'])
        self.assertIn('DIAGNOSTIC measured value: 7', page['source'])
        self.assertEqual(page['next_offset'], 120); self.assertTrue(page['more'])
        self.assertEqual(before, (self.log.read_bytes(), self.log.stat().st_mtime_ns))
        tail = read_page(self.root, str(self.log), page['next_offset'])
        self.assertEqual(len(tail['source'].splitlines()), 26); self.assertFalse(tail['more'])
        self.assertEqual(page['sha256'], tail['sha256'])
        self.log.write_text('rerun changed output\n')
        self.assertNotEqual(read_page(self.root, str(self.log))['sha256'], page['sha256'])

    def test_other_session_files_and_unrecorded_logs_are_rejected(self):
        for name in ['launch.json', 'other.log', 'provider-timing.jsonl']:
            p = self.session / name; p.write_text('private')
            with self.subTest(name=name), self.assertRaises(ValueError):
                read_page(self.root, str(p))

    def test_root_binding_must_match_the_current_task(self):
        self.bind(root=self.base / 'other-project')
        with self.assertRaisesRegex(ValueError, 'different project'):
            read_page(self.root, str(self.log))

    def test_state_cannot_belong_to_a_different_session(self):
        other = self.base / 'other-session'; other.mkdir()
        state = other / 'task-state.json'; state.write_bytes(self.state.read_bytes())
        with patch.dict(os.environ, {'QWEN_WORKFLOW_STATE': str(state)}):
            with self.assertRaises(ValueError): read_page(self.root, str(self.log))

    def test_recorded_escape_and_symlink_escape_are_rejected(self):
        outside = self.base / 'outside.log'; outside.write_text('private')
        self.bind(log=outside)
        with self.assertRaisesRegex(ValueError, 'inside the current session'):
            read_page(self.root, str(outside))
        link = self.session / 'linked.log'; link.symlink_to(outside); self.bind(log=link)
        with self.assertRaisesRegex(ValueError, 'inside the current session'):
            read_page(self.root, str(link))

    def test_no_current_record_means_no_special_access(self):
        self.state.write_text('{}')
        with self.assertRaises(ValueError): read_page(self.root, str(self.log))
        self.bind()
        with patch.dict(os.environ, {'QWEN_WORKFLOW_SESSION': ''}):
            with self.assertRaises(ValueError): read_page(self.root, str(self.log))

    def test_log_text_obeys_existing_byte_and_encoding_budgets(self):
        self.log.write_bytes(b'\xff')
        with self.assertRaisesRegex(ValueError, 'UTF-8'): read_page(self.root, str(self.log))
        self.log.write_text('x' * 13000)
        with self.assertRaisesRegex(ValueError, 'page budget'): read_page(self.root, str(self.log))
        self.log.write_text(('x' * 1000 + '\n') * 30)
        self.assertLess(len(read_page(self.root, str(self.log))['source'].encode()), 12000)


if __name__ == '__main__':
    unittest.main()
