"""Regression tests for interface extraction and context integrity."""
import tempfile
import unittest
from pathlib import Path
from javascript_map import parse_javascript, parse_html
from python_map import parse_python
from project_map import outline, select_context, write_map
from briefs import annotate


class MapTests(unittest.TestCase):
    """Check real parsing edge cases rather than implementation shape."""
    def test_python_interfaces_preserve_types_and_nested_helpers(self):
        """Async signatures and nested private functions remain navigable."""
        parsed = parse_python('''
async def solve(x: int, *, limit=3) -> str:
    """Solve a bounded task."""
    def _helper(value):
        return value + 1
    return str(_helper(x))
''')
        self.assertEqual([s['name'] for s in parsed['symbols']], ['solve', 'solve._helper'])
        self.assertIn('async def solve(x: int, *, limit=3) -> str', parsed['symbols'][0]['signature'])
        self.assertEqual(parsed['symbols'][0]['description'], 'Solve a bounded task.')
        self.assertEqual(parsed['symbols'][1]['description'], '[description missing]')

    def test_javascript_arrows_methods_and_body_omission(self):
        """Strings containing braces do not confuse real syntax parsing."""
        parsed = parse_javascript('''
const add = (x, y = 1) => x + y;
class Worker { async run(job) { return "hidden body { }"; } }
''')
        names = {s['name'] for s in parsed['symbols']}
        self.assertTrue({'add', 'Worker', 'Worker.run'} <= names)
        self.assertNotIn('hidden body', '\n'.join(s['signature'] for s in parsed['symbols']))

    def test_typescript_annotations(self):
        """Typed arrow parameters survive extraction."""
        parsed = parse_javascript('const sum = (a: number, b: number): number => a + b;', '.ts')
        self.assertIn('a: number', parsed['symbols'][0]['signature'])

    def test_owned_arrow_comments_are_briefs_without_inheriting_enclosing_docs(self):
        """Normal comments above const arrows and object properties survive mapping."""
        parsed = parse_javascript('''
/** Build a handle. */
function boot() {
  // Injected random boundary.
  const random = () => Math.random();
  const undocumented = () => 123;
  return {
    /** Inspect current state. */
    getState: () => random()
  };
}
''')
        descriptions = {s['name']: s['description'] for s in parsed['symbols']}
        self.assertEqual(descriptions['boot.random'], 'Injected random boundary.')
        self.assertEqual(descriptions['boot.getState'], 'Inspect current state.')
        self.assertEqual(descriptions['boot.undocumented'], '[description missing]')

    def test_function_body_leading_comment_is_a_brief_not_implementation(self):
        """Preserve local function documentation while omitting executable code."""
        parsed = parse_javascript('function run(x) {\n// Return the next count.\nreturn x + 1;\n}')
        symbol = parsed['symbols'][0]
        self.assertEqual(symbol['description'], 'Return the next count.')
        self.assertNotIn('return x', symbol['contract'])

    def test_explicit_single_object_member_documentation_is_preserved(self):
        for member in ['sample: () => 7', 'sample() { return 7; }']:
            with self.subTest(member=member):
                parsed=parse_javascript('// FIXED.sample returns a repeatable value.\nexport const FIXED = {'+member+'};')
                self.assertEqual(parsed['symbols'][0]['description'], 'FIXED.sample returns a repeatable value.')
                self.assertNotIn('return 7',parsed['symbols'][0]['contract'])

    def test_object_or_class_summary_does_not_document_unrelated_members(self):
        samples=[
            '// A fixed source.\nconst FIXED = { sample: () => 7 };',
            '// OTHER.sample returns a value.\nconst FIXED = { sample: () => 7 };',
            '// FIXED.sampleLater returns a value.\nconst FIXED = { sample: () => 7 };',
            '// FIXED.sample returns a value.\nconst FIXED = { sample: () => 7, other: () => 8 };',
            '// FIXED.sample returns a value.\nclass FIXED { sample() { return 7; } }',
            '// FIXED.sample returns a value.\nconst FIXED = { nested: { sample: () => 7 } };',
        ]
        for source in samples:
            with self.subTest(source=source):
                methods=[s for s in parse_javascript(source)['symbols'] if s['kind']=='function']
                self.assertTrue(methods)
                self.assertTrue(all(s['description']=='[description missing]' for s in methods))

    def test_variables_keep_scope_and_types_without_copying_values(self):
        """Module and class declarations describe interfaces without leaking values."""
        parsed = parse_python('MAX: int = 3\nclass Worker:\n    state: str = "hidden value"\n')
        self.assertEqual(parsed['variables'][0]['name'], 'MAX')
        self.assertEqual(parsed['variables'][1]['scope'], 'Worker')
        self.assertNotIn('hidden value', str(parsed['variables']))
        javascript = parse_javascript('const config = {secret: "hidden"};')
        self.assertEqual(javascript['variables'][0]['name'], 'config')

    def test_inline_html_has_original_lines_and_skips_json(self):
        """Configuration scripts are not mistaken for executable JavaScript."""
        parsed = parse_html('<html>\n<script src="main.js"></script>\n<script>\nfunction go(x) { return x; }\n</script>\n<script type="application/ld+json">{"a":1}</script>')
        self.assertEqual(parsed['imports'], ['main.js'])
        self.assertEqual(parsed['symbols'][0]['line'], 4)

    def test_syntax_error_is_visible(self):
        """Broken JavaScript cannot silently produce an incomplete interface map."""
        with self.assertRaises(ValueError):
            parse_javascript('function broken( {')

    def test_briefs_are_discarded_when_source_hash_changes(self):
        """Reviewed descriptions never silently certify later source changes."""
        import json
        record = {'path': 'a.py', 'sha256': 'original', 'symbols': [{'name': 'f', 'description': '[description missing]'}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'briefs.json'
            path.write_text(json.dumps({'files': {'a.py': {'sha256': 'original', 'symbols': {'f': 'Verified contract'}}}}))
            self.assertEqual(annotate([record], str(path)), [])
            self.assertEqual(record['symbols'][0]['description'], 'Verified contract')
            fresh = {**record, 'sha256': 'edited', 'symbols': [{'name': 'f', 'description': '[description missing]'}]}
            self.assertEqual(annotate([fresh], str(path)), ['a.py'])
            self.assertEqual(fresh['symbols'][0]['description'], '[description missing]')

    def test_context_overflow_fails_instead_of_clipping(self):
        """A caller receives a complete outline or a budget error."""
        record = {'path': 'a.py', 'sha256': 'abc', 'description': 'A',
                  'symbols': [], 'imports': [], 'error': None, 'lines': 1}
        data = {'files': [record], 'snapshot': 'abc'}
        with self.assertRaises(ValueError):
            select_context(data, ['a.py'], 5)
        self.assertEqual(select_context(data, ['a.py'], 1000), outline(record))

    def test_named_interface_batch_excludes_unrequested_functions(self):
        """Smart navigation batches known functions without expanding unrelated scope."""
        parsed = parse_python('def first():\n    return 1\ndef second():\n    return 2\ndef other():\n    return 3\n')
        record = {'path':'a.py','sha256':'abc','error':None,**parsed}
        result = select_context({'files':[record]}, ['a.py'], 1000, 'first second')
        self.assertIn('first:', result)
        self.assertIn('second:', result)
        self.assertNotIn('other:', result)

    def test_deleted_interfaces_are_removed_without_deleting_user_files(self):
        """Regeneration removes stale owned output and preserves unrelated artifacts."""
        record = {'path': 'a.py', 'sha256': 'abc', 'description': 'A',
                  'symbols': [], 'imports': [], 'error': None, 'lines': 1}
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            write_map({'files': [record], 'snapshot': 'first'}, dest)
            (dest / 'keep.txt').write_text('user artifact')
            write_map({'files': [], 'snapshot': 'second'}, dest)
            self.assertFalse((dest / 'prototypes/a.py.txt').exists())
            self.assertEqual((dest / 'keep.txt').read_text(), 'user artifact')


if __name__ == '__main__':
    unittest.main()
