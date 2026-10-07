"""Distill actual Pi events into bounded evidence without implementation leakage."""
import json
from pathlib import Path
import tempfile
import unittest
from execution_audit import summarize


class AuditTests(unittest.TestCase):
    def test_success_errors_compaction_and_repeated_content_without_bodies(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pi.log'
            rows = []
            for i in range(3):
                rows += [{'type': 'tool_execution_start', 'toolCallId': str(i), 'toolName': 'write',
                          'args': {'path': 'source.py', 'content': 'PRIVATE_IMPLEMENTATION_SENTINEL'}},
                         {'type': 'tool_execution_end', 'toolCallId': str(i), 'toolName': 'write',
                          'isError': i == 2, 'result': {'content': [{'type': 'text', 'text': 'blocked'}]}}]
            rows += [{'type': 'compaction_end', 'aborted': False}, {'type': 'compaction_end', 'aborted': True},
                     {'type': 'message_update', 'delta': 'PRIVATE_REASONING_SENTINEL'}]
            path.write_text('partial line\n' + '\n'.join(map(json.dumps, rows)) + '\n{"unfinished":')
            result = summarize(path, ['source.py'])
            self.assertEqual(result['compactions'], 1)
            self.assertEqual(result['mutations']['source.py']['successful_mutations'], 2)
            self.assertEqual(result['mutations']['source.py']['identical_consecutive_writes'], 1)
            self.assertEqual(result['recent_tool_errors'], [{'tool': 'write', 'error': 'blocked'}])
            self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_only_declared_paths_and_bounded_recent_errors_are_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pi.log'
            rows = [{'type': 'tool_execution_start', 'toolCallId': '1', 'toolName': 'write',
                     'args': {'path': '/tmp/outside.py', 'content': 'secret'}},
                    {'type': 'tool_execution_end', 'toolCallId': '1', 'toolName': 'write', 'isError': False}]
            rows += [{'type': 'tool_execution_end', 'toolName': 'edit', 'isError': True,
                      'result': {'content': [{'type': 'text', 'text': 'e' * 1000}]}}] * 20
            path.write_text('\n'.join(map(json.dumps, rows)))
            result = summarize(path, ['source.py'])
            self.assertEqual(result['mutations'], {})
            self.assertEqual(len(result['recent_tool_errors']), 4)
            self.assertTrue(all(len(e['error']) <= 240 for e in result['recent_tool_errors']))
        self.assertEqual(summarize(None, []), {})
