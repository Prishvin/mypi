"""Tests for task scope, size ratchets and stale validation evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from retrieval import source_path, read_fixture
from policy import validate_change
from tasks import begin, check, run_tests, ensure_test_evidence, inherit_baseline
from shadow import refresh


class PolicyTests(unittest.TestCase):
    """Exercise task boundaries against changes that must be rejected."""
    def test_legacy_size_can_shrink_but_not_grow(self):
        """Existing debt does not prevent fixes, while added debt is rejected."""
        old = {'path': 'studio/a.py', 'sha256': 'a', 'lines': 900, 'symbols': [], 'error': None}
        smaller = {**old, 'sha256': 'b', 'lines': 899}
        bigger = {**old, 'sha256': 'c', 'lines': 901}
        self.assertTrue(validate_change({'files': [old]}, {'files': [smaller]}, [old['path']])['passed'])
        self.assertFalse(validate_change({'files': [old]}, {'files': [bigger]}, [old['path']])['passed'])

    def test_existing_function_description_cannot_disappear(self):
        """A later patch cannot silently erase a previously documented interface."""
        symbol = {'name': 'step', 'kind': 'function', 'lines': 2, 'description': 'Advance state.'}
        old = {'path': 'a.py', 'sha256': 'a', 'lines': 3, 'symbols': [symbol], 'error': None}
        new = {**old, 'sha256': 'b', 'symbols': [{**symbol, 'description': '[description missing]'}]}
        result = validate_change({'files': [old]}, {'files': [new]}, ['a.py'])
        self.assertFalse(result['passed'])
        self.assertTrue(any('description was removed' in v for v in result['violations']))

    def test_changes_outside_scope_fail(self):
        """Adding a file outside the frozen task list is visible."""
        new = {'path': 'studio/b.py', 'sha256': 'a', 'lines': 5, 'symbols': [], 'error': None}
        result = validate_change({'files': []}, {'files': [new]}, ['studio/a.py'])
        self.assertFalse(result['passed'])


class TaskTests(unittest.TestCase):
    """Use a real temporary repository and a real CPU-only unittest command."""
    def setUp(self):
        """Create a tiny isolated project with no external services."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'studio').mkdir()
        (self.root / 'studio/a.py').write_text('def add(x):\n    """Add one."""\n    return x + 1\n')
        (self.root / 'studio/test_a.py').write_text('import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        """Confirm a result."""\n        self.assertEqual(1 + 1, 2)\n')
        self.state = Path(self.temp.name) / 'state.json'
        task = {'goal': 'Fix add', 'acceptance': ['Adds correctly'],
                'files': ['studio/a.py', 'studio/test_a.py'],
                'tests': [[sys.executable, '-m', 'unittest', 'discover', '-s', 'studio']]}
        begin(self.root, ['studio'], task, self.state)

    def test_missing_new_test_file_and_zero_tests_cannot_complete(self):
        """Creating only implementation must not trigger early stop after empty discovery."""
        new=self.root/'empty';new.mkdir()
        state=self.state.with_name('empty-state.json')
        task={'goal':'Create parser and tests','acceptance':['Function and tests exist'],
              'files':['parser.py','test_parser.py'],'tests':[[sys.executable,'-m','unittest','-v']]}
        begin(new,['.'],task,state)
        (new/'parser.py').write_text('def parse(x):\n    """Parse input."""\n    return x\n')
        result=run_tests(state)
        self.assertIn(result['results'][0]['exit_code'],[0,5])
        self.assertEqual(result['results'][0]['tests_collected'],0)
        gate=check(state)
        self.assertFalse(gate['passed'])
        self.assertTrue(any('new files' in v for v in gate['violations']))
        self.assertTrue(any('zero tests' in v for v in gate['violations']))
        (new/'test_parser.py').write_text('import unittest\nfrom parser import parse\nclass T(unittest.TestCase):\n    def test_parse(self):\n        """Test parse."""\n        self.assertEqual(parse(1),1)\n')
        run_tests(state);self.assertTrue(check(state)['passed'])

    def test_validation_becomes_stale_after_edit(self):
        """Passing tests do not certify a later mutation."""
        self.assertFalse(check(self.state)['passed'])
        run_tests(self.state)
        self.assertTrue(check(self.state)['passed'])
        (self.root / 'studio/a.py').write_text('def add(x):\n    """Add one."""\n    return x + 2\n')
        self.assertFalse(check(self.state)['passed'])

    def test_failed_test_is_not_accepted(self):
        """An actual unittest failure blocks completion."""
        path = self.root / 'studio/test_a.py'
        path.write_text(path.read_text().replace('1 + 1, 2', '1 + 1, 3'))
        evidence = run_tests(self.state)
        self.assertNotEqual(evidence['results'][0]['exit_code'], 0)
        self.assertFalse(check(self.state)['passed'])

    def test_final_verifier_reuses_current_results_and_retests_after_edit(self):
        """Completion supplies missing evidence without repeating already current tests."""
        with patch('tasks.run_tests', wraps=run_tests) as executed:
            ensure_test_evidence(self.state)
            ensure_test_evidence(self.state)
            self.assertEqual(executed.call_count, 1)
            path = self.root / 'studio/a.py'
            path.write_text(path.read_text().replace('x + 1', 'x + 2'))
            ensure_test_evidence(self.state)
            self.assertEqual(executed.call_count, 2)

    def test_retry_does_not_grandfather_failed_new_size_debt(self):
        """A failed oversized function stays new relative to the original todo."""
        path = self.root / 'studio/a.py'
        path.write_text('def add(x):\n    """Add one."""\n    value=x\n' + '    value += 1\n' * 62 + '    return value\n')
        original = json.loads(self.state.read_text())
        retry = self.state.with_name('retry.json')
        begin(self.root, ['studio'], original['task'], retry)
        inherit_baseline(retry, self.state)
        run_tests(retry)
        self.assertTrue(any('Function size' in v for v in check(retry)['violations']))

    def test_scope_escape_is_rejected(self):
        """Task contracts cannot declare paths outside the project."""
        task = json.loads(self.state.read_text())['task']
        task['files'] = ['../other.py']
        with self.assertRaises(ValueError):
            begin(self.root, ['studio'], task, self.state.with_name('other.json'))

    def test_shadow_required_and_corruption_blocks_completion(self):
        """Passing tests cannot complete a task with missing or modified prototypes."""
        run_tests(self.state)
        data = json.loads(self.state.read_text())
        shadow = Path(data['shadow'])
        (shadow / 'prototypes/studio/a.py.txt').write_text('stale interface')
        result = check(self.state)
        self.assertFalse(result['passed'])
        self.assertTrue(any('Shadow' in v for v in result['violations']))
        refresh(self.root, ['studio'], shadow)
        self.assertTrue(check(self.state)['passed'])

    def test_external_fixtures_are_readonly_and_hash_bound(self):
        """Allow only the declared external fixture; reject altered fixture evidence."""
        fixture = Path(self.temp.name) / 'acceptance.py'
        fixture.write_text('print("ok")\n')
        state = self.state.with_name('external-state.json')
        task = {'goal': 'Fix add', 'acceptance': ['Correct result'], 'files': ['studio/a.py'],
                'tests': [[sys.executable, str(fixture)]]}
        begin(self.root, ['studio'], task, state)
        with patch.dict('os.environ', {'QWEN_WORKFLOW_STATE': str(state)}):
            self.assertEqual(source_path(self.root, str(fixture)), fixture.resolve())
            self.assertIn('print("ok")', read_fixture(self.root, str(fixture))['source'])
            with self.assertRaises(ValueError):
                read_fixture(self.root, 'studio/a.py')
            fixture.write_text('print("changed test")\n')
            with self.assertRaises(ValueError):
                source_path(self.root, str(fixture))
        run_tests(state)
        result = check(state)
        self.assertFalse(result['passed'])
        self.assertTrue(any('immutable' in v for v in result['violations']))


if __name__ == '__main__':
    unittest.main()
