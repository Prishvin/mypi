"""Deadline feedback is factual, scoped and independent of progress/acceptance."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from progress_observer import check, deadline


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name).resolve()
        self.identity = {'project': str(self.session), 'task': 'T1'}
        self.launch = {'role': 'code', 'project': str(self.session),
                       'state': str(self.session / 'task-state.json'), 'timeout_seconds': 900,
                       'command': ['PRIVATE_PROMPT'], 'credentials': 'PRIVATE_AUTH'}
        self.process = {'started_epoch': 1000, 'process_group': 9999}
        self.write('launch.json', self.launch)
        self.write('process.json', self.process)
        self.write('task-state.json', {'before': {'root': str(self.session)},
                                      'task': {'id': 'T1', 'files': ['source.py']}})
        (self.session / 'source.py').write_text('PRIVATE_SOURCE')

    def write(self, name, value):
        (self.session / name).write_text(json.dumps(value))

    def test_threshold_uses_process_start_not_prepare_time(self):
        self.launch['started_epoch'] = 1
        self.write('launch.json', self.launch)
        before = deadline(self.session, self.identity, 1599)
        self.assertFalse(before['near_deadline'])
        at = deadline(self.session, self.identity, 1600)
        self.assertEqual(at['remaining_seconds'], 300)
        self.assertEqual(at['elapsed_seconds'], 600)
        self.assertTrue(at['near_deadline'])
        self.assertNotIn('PRIVATE', json.dumps(at))
        self.assertNotIn('process_group', at)

    def test_expiry_is_zero_notice_not_a_deadline_extension(self):
        at = deadline(self.session, self.identity, 1901)
        self.assertEqual(at['remaining_seconds'], 0)
        self.assertEqual(at['timeout_seconds'], 900)
        self.assertTrue(at['near_deadline'])
        self.assertEqual(json.loads((self.session / 'launch.json').read_text()), self.launch)

    def test_short_and_long_limits_have_bounded_notice_window(self):
        for timeout, remaining, expected in [(30, 30, True), (120, 120, True),
                                               (600, 301, False), (600, 300, True),
                                               (600, 239, True), (2700, 301, False), (2700, 300, True)]:
            with self.subTest(timeout=timeout, remaining=remaining):
                self.write('launch.json', {**self.launch, 'timeout_seconds': timeout})
                self.assertEqual(deadline(self.session, self.identity, 1000 + timeout - remaining)['near_deadline'], expected)

    def test_backward_wall_clock_is_clamped_not_negative_elapsed(self):
        at = deadline(self.session, self.identity, 900)
        self.assertEqual(at['elapsed_seconds'], 0)
        self.assertEqual(at['remaining_seconds'], 900)

    def test_missing_optional_timing_keeps_legacy_sessions_working(self):
        self.write('launch.json', {**self.launch, 'timeout_seconds': None})
        self.assertIsNone(deadline(self.session, self.identity, 1800))
        (self.session / 'process.json').unlink()
        self.assertIsNone(deadline(self.session, self.identity, 1800))

    def test_wrong_binding_and_invalid_values_fail_visibly(self):
        for change in [{'role': 'architect'}, {'project': str(self.session / 'other')},
                       {'state': str(self.session / 'other.json')}, {'timeout_seconds': True},
                       {'timeout_seconds': -1}, {'timeout_seconds': float('nan')}]:
            with self.subTest(change=change):
                self.write('launch.json', {**self.launch, **change})
                with self.assertRaises(ValueError):
                    deadline(self.session, self.identity, 1800)
        self.write('launch.json', self.launch)
        self.write('process.json', {'started_epoch': 'bad'})
        with self.assertRaises(ValueError):
            deadline(self.session, self.identity, 1800)

    def test_clock_does_not_count_as_progress_or_change_stagnation_policy(self):
        with patch('progress_observer.time.time', return_value=1600):
            first = check(self.session)
        with patch('progress_observer.time.time', return_value=1800):
            second = check(self.session)
        self.assertEqual(first['status'], 'continue')
        self.assertEqual(second['status'], 'continue')
        self.assertEqual(second['rounds_without_progress'], 0)
        self.assertEqual(second['deadline']['remaining_seconds'], 100)
        self.assertFalse((self.session / 'progress-stop.json').exists())
        with (self.session / 'execution-events.jsonl').open('a') as out:
            out.write('{"kind":"round"}\n' * 4)
        with patch('progress_observer.time.time', return_value=1901):
            stopped = check(self.session)
        self.assertEqual(stopped['status'], 'stop')
        self.assertEqual(stopped['deadline']['remaining_seconds'], 0)
        self.assertEqual(json.loads((self.session / 'progress-stop.json').read_text())['reason'], 'no_progress')


if __name__ == '__main__':
    unittest.main()
