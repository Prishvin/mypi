"""Verify brief architectural decisions remain current and context stays bounded."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import architecture_map
from project_map import scan, write_map
import shadow


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'logic.py').write_text('"""Pure rules."""\ndef decide(x):\n    """Evaluate one move."""\n    return "SECRET_BODY"\n')
        self.output = Path(self.temp.name) / 'shadow'

    def test_map_has_decisions_and_resolvable_shadow_links_without_bodies(self):
        (self.root / 'architecture.md').write_text('Rules are pure; the browser owns rendering.\n')
        data = scan(self.root, ['.'])
        write_map(data, self.output)
        text = (self.output / 'architecture.md').read_text()
        self.assertIn('Rules are pure', text)
        self.assertIn('prototypes/logic.py.txt', text)
        self.assertTrue((self.output / 'prototypes/logic.py.txt').is_file())
        self.assertNotIn('SECRET_BODY', text)
        self.assertNotIn('SECRET_BODY', (self.output / 'prototypes/logic.py.txt').read_text())

    def test_decision_change_invalidates_snapshot_and_corrupted_map_blocks_completion(self):
        doc = self.root / 'architecture.md'
        doc.write_text('Use pure functions.\n')
        before = scan(self.root, ['.'])
        write_map(before, self.output)
        frozen = {'shadow': str(self.output)}
        self.assertEqual(shadow.verify(frozen, before), [])
        (self.output / 'architecture.md').write_text('Outdated decisions')
        self.assertIn('architecture map is stale', shadow.verify(frozen, before)[0])
        doc.write_text('Use pure functions with injected time.\n')
        after = scan(self.root, ['.'])
        self.assertNotEqual(before['snapshot'], after['snapshot'])
        write_map(after, self.output)
        self.assertEqual(shadow.verify(frozen, after), [])

    def test_selected_map_and_pages_do_not_expand_to_unrelated_modules(self):
        (self.root / 'unrelated.py').write_text('"""Unrelated feature."""\n')
        data = scan(self.root, ['.'])
        text = architecture_map.render(data, ['logic.py'])
        self.assertIn('logic.py', text)
        self.assertNotIn('unrelated.py', text)
        self.assertIn('Modules 1 of 2', architecture_map.render(data, limit=1))

    def test_architecture_is_readable_through_bounded_interface_context(self):
        from project_map import select_context
        (self.root / 'architecture.md').write_text('Browser depends on pure rules.\n')
        text = select_context(scan(self.root, ['.']), ['architecture.md'], 4096)
        self.assertIn('Browser depends on pure rules', text)
        self.assertNotIn('SECRET_BODY', text)

    def test_architecture_edits_require_explicit_task_scope(self):
        from policy import validate_change
        before = scan(self.root, ['.'])
        (self.root / 'architecture.md').write_text('Rules stay pure.\n')
        after = scan(self.root, ['.'])
        self.assertFalse(validate_change(before, after, ['logic.py'])['passed'])
        self.assertTrue(validate_change(before, after, ['logic.py', 'architecture.md'])['passed'])

    def test_oversized_decisions_and_symlinks_are_rejected(self):
        doc = self.root / 'architecture.md'
        doc.write_text('x\n' * 81)
        with self.assertRaisesRegex(ValueError, '80 lines'):
            scan(self.root, ['.'])
        doc.unlink()
        doc.symlink_to(self.root / 'logic.py')
        with self.assertRaisesRegex(ValueError, 'regular project file'):
            scan(self.root, ['.'])


if __name__ == '__main__':
    unittest.main()
