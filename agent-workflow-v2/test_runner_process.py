"""Record launcher-owned deadlines even when the outer watchdog did not fire."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from runner_process import invoke, read


class ProcessTests(unittest.TestCase):
    def test_child_exit_124_is_a_timeout_and_other_exit_codes_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            for code in (0, 1, 124):
                with self.subTest(code=code), patch('runner_process.memory_sample', return_value={}):
                    output = Path(folder) / str(code)
                    result = invoke([sys.executable, '-c', f'import sys;sys.exit({code})'], output, 5)
                    self.assertEqual(result['exit_code'], code)
                    self.assertEqual(result['timed_out'], code == 124)
                    self.assertEqual(read(output / 'result.json'), result)
