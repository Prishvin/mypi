"""Prove token boundaries, architecture-first enforcement and narrow prototype reads."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from project_map import scan, write_map
import shadow_navigation as navigation


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.root, self.session = base / 'project', base / 'session'
        self.root.mkdir(); self.session.mkdir()
        (self.root / 'maths.py').write_text('"""Pure arithmetic."""\ndef double(x):\n    """Double a value."""\n    return "SECRET_BODY"\n')
        self.data = scan(self.root, ['.'])

    def test_threshold_is_strictly_greater_than_32768(self):
        for total, large in [(32768, False), (32769, True)]:
            values = iter([total - 1, 1])
            policy = navigation.measure(self.data, lambda text: next(values))
            self.assertEqual(policy['total_tokens'], total)
            self.assertEqual(policy['architecture_only_navigation'], large)

    def test_counts_match_written_artifacts_without_duplicate_catalogs(self):
        output = self.session / 'shadow'
        write_map(self.data, output)
        policy = navigation.measure(self.data)
        self.assertEqual(policy['shadow_tokens'], navigation.count((output / 'ALL-PROTOTYPES.txt').read_text()))
        self.assertEqual(policy['architecture_tokens'], navigation.count((output / 'architecture.md').read_text()))
        self.assertNotIn('SECRET_BODY', (output / 'ALL-PROTOTYPES.txt').read_text())

    def test_large_scope_requires_architecture_and_rejects_alternate_global_maps(self):
        policy = {'architecture_only_navigation': True}
        state = {'architecture_read': False, 'seen_paths': []}
        for command in ('context', 'locate', 'save-plan'):
            with self.assertRaisesRegex(ValueError, 'read project_map architecture'):
                navigation.authorize(policy, state, command, ['maths.py'])
        state.update(architecture_read=True, seen_paths=['maths.py'])
        navigation.authorize(policy, state, 'context', ['maths.py'])
        navigation.authorize(policy, state, 'locate', ['maths.py'])
        navigation.authorize(policy, state, 'save-plan')
        for command, paths, error in [('catalog', [], 'not catalog'),
                                     ('locate', [], '1-5 explicit'),
                                     ('context', ['other.py'], 'architecture page'),
                                     ('context', [str(i) for i in range(6)], '1-5 explicit')]:
            with self.assertRaisesRegex(ValueError, error):
                navigation.authorize(policy, state, command, paths)

    def test_small_navigation_and_executor_are_unaffected(self):
        navigation.authorize({'architecture_only_navigation': False}, {}, 'catalog')
        with patch.dict(os.environ, {'QWEN_WORKFLOW_ROLE': 'code'}):
            self.assertIsNone(navigation.planning_context(argparse.Namespace(command='context'), self.root, ['.']))

    def test_selected_token_limit_fails_without_clipping(self):
        policy = {'architecture_only_navigation': True}
        navigation.check_selected(policy, 'contracts', lambda text: 8192)
        with self.assertRaisesRegex(ValueError, '8192 tokens'):
            navigation.check_selected(policy, 'contracts', lambda text: 8193)

    def test_changed_snapshot_requires_new_architecture_navigation(self):
        with patch.dict(os.environ, {'QWEN_WORKFLOW_ROLE': 'architect', 'QWEN_WORKFLOW_SESSION': str(self.session)}):
            navigation.initialize(self.data, self.session)
            args = argparse.Namespace(command='architecture', paths=None)
            context = navigation.planning_context(args, self.root, ['.'])
            navigation.record_architecture(context, None, 0, 10)
            (self.root / 'architecture.md').write_text('New ownership decisions.\n')
            new_context = navigation.planning_context(args, self.root, ['.'])
            self.assertFalse(new_context[2]['architecture_read'])
            self.assertEqual(new_context[2]['seen_paths'], [])
            self.assertNotEqual(context[1]['snapshot'], new_context[1]['snapshot'])

    def test_real_large_project_cli_pages_selects_and_scopes_search(self):
        for i in range(20):
            functions = ''.join(f'def function_{j}(value: int) -> int:\n    """Return a deterministic number for this module interface."""\n    return "SECRET_BODY"\n' for j in range(80))
            (self.root / f'module_{i:02}.py').write_text('"""Independent pure component."""\n' + functions)
        data = scan(self.root, ['.'])
        policy = navigation.initialize(data, self.session)
        self.assertGreater(policy['total_tokens'], 32768)
        env = {**os.environ, 'QWEN_WORKFLOW_ROLE': 'architect', 'QWEN_WORKFLOW_SESSION': str(self.session)}
        def run(*args):
            return subprocess.run([sys.executable, str(Path(__file__).with_name('workflow.py')),
                '--root', str(self.root), *args], env=env, text=True, capture_output=True)
        self.assertNotEqual(run('context', 'module_00.py').returncode, 0)
        page = run('architecture')
        self.assertEqual(page.returncode, 0, page.stderr)
        self.assertIn('Modules 10 of 21', page.stdout)
        self.assertNotIn('module_19.py', page.stdout)
        self.assertNotEqual(run('context', 'module_19.py').returncode, 0)
        self.assertNotEqual(run('catalog').returncode, 0)
        self.assertNotEqual(run('locate', 'function_1').returncode, 0)
        selected = run('context', 'module_00.py', '--symbol', 'function_1')
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertIn('function_1:', selected.stdout)
        self.assertNotIn('SECRET_BODY', selected.stdout)
        located = run('locate', 'function_1', '--paths', 'module_00.py')
        self.assertEqual(located.returncode, 0, located.stderr)
        self.assertTrue(all(row['path'] == 'module_00.py' for row in json.loads(located.stdout)['matches']))
        self.assertEqual(run('architecture', '--offset', '10').returncode, 0)
        self.assertEqual(run('architecture', '--offset', '20').returncode, 0)
        self.assertEqual(run('context', 'module_19.py', '--symbol', 'function_1').returncode, 0)


if __name__ == '__main__':
    unittest.main()
