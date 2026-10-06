"""Bounded source retrieval tests use tiny isolated CPU fixtures."""
from pathlib import Path
import tempfile
import unittest
from retrieval import read_symbol, read_symbols, variables, search, source_path


class RetrievalTests(unittest.TestCase):
    """Check exact symbol lookup, bounded pages and literal grep semantics."""
    def setUp(self):
        """Create source with adjacent functions to catch excessive reads."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'a.py').write_text('def wanted(x):\n    """Return a value."""\n    return x\n\ndef unrelated():\n    return "do not include this body"\n')

    def test_symbol_read_excludes_adjacent_implementation(self):
        """A named function request never includes the following body."""
        result = read_symbol(self.root, 'a.py', 'wanted')
        self.assertIn('return x', result['source'])
        self.assertNotIn('do not include', result['source'])
        self.assertFalse(result['more'])

    def test_missing_batch_member_keeps_valid_source_and_boundaries(self):
        result = read_symbols(self.root, 'a.py', ['wanted', 'invented'])
        self.assertEqual([s['symbol'] for s in result['symbols']], ['wanted'])
        self.assertEqual(result['errors'][0]['symbol'], 'invented')
        self.assertNotIn('do not include this body', str(result))
        with self.assertRaises(ValueError):
            read_symbols(self.root, 'a.py', ['wanted'] * 9)
        with self.assertRaises(ValueError):
            read_symbols(self.root, '../outside.py', ['wanted'])

    def test_multi_name_variables_do_not_leak_values(self):
        (self.root / 'vars.py').write_text('TURN_SPEED=2\nMAX_DT=0.1\nSECRET="hidden initializer"\n')
        result = variables(self.root, 'vars.py', 'TURN_SPEED MAX_DT')
        self.assertEqual({v['name'] for v in result['variables']}, {'TURN_SPEED', 'MAX_DT'})
        self.assertNotIn('hidden initializer', str(result))

    def test_symbol_pages_are_bounded(self):
        """Long functions require explicit subsequent page requests."""
        (self.root / 'long.py').write_text('def long():\n' + '    x = 1\n' * 200)
        result = read_symbol(self.root, 'long.py', 'long')
        self.assertEqual(len(result['source'].splitlines()), 100)
        self.assertTrue(result['more'])

    def test_grep_treats_pattern_literally(self):
        """Regex punctuation is not broadened by default."""
        result = search(self.root, ['a.py'], 'wanted(x)')
        self.assertIn('def wanted(x)', result['matches'])
        self.assertNotIn('unrelated', result['matches'])

    def test_escaping_paths_are_rejected(self):
        """Retrieval cannot follow project-relative paths outside the project."""
        with self.assertRaises(ValueError):
            source_path(self.root, '../outside.py')

    def test_symbol_names_can_repeat_in_distinct_objects(self):
        """Multiple same-named JavaScript methods receive unique locators."""
        (self.root / 'objects.js').write_text('const a = {run() { return 1; }}; const b = {run() { return 2; }};')
        first = read_symbol(self.root, 'objects.js', 'run')
        second = read_symbol(self.root, 'objects.js', 'run#2')
        self.assertIn('return 1', first['source'])
        self.assertIn('return 2', second['source'])
        self.assertNotIn('return 2', first['source'])
        self.assertNotIn('return 1', second['source'])

    def test_nested_ambiguous_names_offer_qualified_candidates(self):
        """An ambiguous short name returns actionable scopes without exposing bodies."""
        (self.root / 'nested.js').write_text('function a(){function restart(){return 1;}} '
                                             'function b(){function restart(){return 2;}}')
        with self.assertRaises(ValueError) as error:
            read_symbol(self.root, 'nested.js', 'restart')
        self.assertIn('a.restart', str(error.exception))
        self.assertIn('b.restart', str(error.exception))
        self.assertNotIn('return 1', str(error.exception))
        self.assertIn('return 1', read_symbol(self.root, 'nested.js', 'a.restart')['source'])

    def test_inline_html_and_decorators_keep_precise_spans(self):
        """Inline scripts and decorated functions preserve their true boundaries."""
        (self.root / 'view.html').write_text('<script\n type="module">function go() { return 1; }</script><p>outside</p>')
        inline = read_symbol(self.root, 'view.html', 'go')
        self.assertNotIn('<script', inline['source'])
        self.assertNotIn('outside', inline['source'])
        (self.root / 'decorated.py').write_text('@cache\ndef go(x):\n    return x\n')
        self.assertIn('@cache', read_symbol(self.root, 'decorated.py', 'go')['source'])


if __name__ == '__main__':
    unittest.main()
