"""Exact declaration reads must stay bounded, scoped and separate from shadow metadata."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from project_map import inspect_file, outline
from retrieval import read_symbol, read_symbols, variables


class VariableRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def write(self, name, text):
        (self.root / name).write_text(text)
        return name

    def test_js_same_line_utf8_and_multiline_object(self):
        path = self.write('a.mjs', 'const prefix="é", COUNT=7, secret="adjacent";\n'
                          'export const CONFIG = {\n  label: "界",\n  nested: [1, 2]\n};\n')
        count = read_symbol(self.root, path, 'COUNT')
        self.assertEqual(count['source'], '1: COUNT=7')
        config = read_symbol(self.root, path, 'CONFIG')
        self.assertEqual(config['total_lines'], 4)
        self.assertIn('label: "界"', config['source'])
        self.assertNotIn('adjacent', str(config))

    def test_typescript_class_field_and_unique_leaf(self):
        path = self.write('a.ts', 'class Store {\n limit: number = 8;\n}\n')
        found = read_symbol(self.root, path, 'limit')
        self.assertEqual(found['symbol'], 'Store.limit')
        self.assertEqual(found['source'], '2: limit: number = 8')
        self.assertEqual(read_symbol(self.root, path, 'Store.limit')['source'], found['source'])

    def test_ambiguous_scopes_and_repeated_assignments_are_not_guessed(self):
        path = self.write('a.js', 'function a(){const count=1;} function b(){const count=2;}')
        with self.assertRaisesRegex(ValueError, 'a.count.*b.count'):
            read_symbol(self.root, path, 'count')
        self.assertEqual(read_symbol(self.root, path, 'a.count')['source'], '1: count=1')
        path = self.write('a.py', 'count = 1\ncount = 2\n')
        with self.assertRaisesRegex(ValueError, 'repeated declarations'):
            read_symbol(self.root, path, 'count')

    def test_exact_variable_beats_nested_callable_leaf(self):
        path = self.write('a.py', 'value = 4\ndef outer():\n    def value():\n        return 2\n')
        self.assertEqual(read_symbol(self.root, path, 'value')['source'], '1: value = 4')

    def test_arrow_retains_callable_span_without_duplicate_variable_match(self):
        path = self.write('a.js', 'const wanted = (x) => x + 1, other = "exclude";')
        found = read_symbol(self.root, path, 'wanted')
        self.assertEqual(found['source'], '1: (x) => x + 1')

    def test_python_byte_spans_annotation_chained_and_destructuring(self):
        path = self.write('a.py', 'prefix="é"; COUNT: int = 3; secret="adjacent"\n'
                          'CONFIG: dict = {\n "name": "界",\n}\nleft = right = 9\na, b = (1, 2)\n')
        self.assertEqual(read_symbol(self.root, path, 'COUNT')['source'], '1: COUNT: int = 3')
        self.assertEqual(read_symbol(self.root, path, 'CONFIG')['total_lines'], 3)
        self.assertEqual(read_symbol(self.root, path, 'right')['source'], '5: left = right = 9')
        self.assertEqual(read_symbol(self.root, path, 'b')['source'], '6: a, b = (1, 2)')

    def test_html_script_byte_offsets_exclude_markup_and_other_scripts(self):
        path = self.write('a.html', '<p>é</p><script\n type="module">const FIRST="界";</script>\n'
                          '<script>const SECOND=2, secret="exclude";</script><p>outside</p>')
        self.assertEqual(read_symbol(self.root, path, 'FIRST')['source'], '2: FIRST="界"')
        self.assertEqual(read_symbol(self.root, path, 'SECOND')['source'], '3: SECOND=2')

    def test_metadata_and_outline_never_include_initializer(self):
        path = self.write('a.js', 'const CONFIG = {key:"private initializer"};')
        record = inspect_file(self.root / path, self.root)
        self.assertNotIn('private initializer', json.dumps(record['variables']))
        self.assertNotIn('private initializer', outline(record))
        self.assertNotIn('private initializer', str(variables(self.root, path, 'CONFIG')))

    def test_pages_and_byte_limits_apply_to_variable_definitions(self):
        path = self.write('a.js', 'const DATA = [\n' + '  1,\n' * 140 + '];')
        first = read_symbol(self.root, path, 'DATA')
        self.assertEqual(first['next_offset'], 100)
        self.assertTrue(first['more'])
        last = read_symbol(self.root, path, 'DATA', first['next_offset'])
        self.assertFalse(last['more'])
        self.assertEqual(len(last['source'].splitlines()), 42)
        path = self.write('wide.js', 'const DATA="' + 'x' * 13000 + '";')
        with self.assertRaisesRegex(ValueError, 'too large'):
            read_symbol(self.root, path, 'DATA')

    def test_empty_batch_fails_cli_but_partial_success_keeps_valid_source(self):
        path = self.write('a.js', 'const FIRST=1, SECOND=2;')
        failed = read_symbols(self.root, path, ['missing', 'absent'])
        self.assertFalse(failed['passed'])
        self.assertEqual(len(failed['errors']), 2)
        partial = read_symbols(self.root, path, ['FIRST', 'missing'])
        self.assertTrue(partial['passed'])
        self.assertEqual(partial['symbols'][0]['symbol'], 'FIRST')
        cli = Path(__file__).with_name('workflow.py')
        for names, expected in [(['missing', 'absent'], 1), (['FIRST', 'missing'], 0), (['FIRST', 'SECOND'], 0)]:
            with self.subTest(names=names):
                result = subprocess.run([sys.executable, str(cli), '--root', str(self.root),
                                         'read-symbols', path, *names], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(json.loads(result.stdout)['passed'], expected == 0)


if __name__ == '__main__':
    unittest.main()
