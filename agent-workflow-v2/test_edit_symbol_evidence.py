"""Parsed-name fallback provides current evidence without fuzzy edits or execution."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from edit_symbol_evidence import locate
from edit_recovery import collect, encoded_size


class SymbolEvidenceTests(unittest.TestCase):
    def test_changed_function_signature_returns_current_body(self):
        current='export function convert(value, limit = 2) {\n  return value.slice(0, limit);\n}\n'
        old='function convert(items, limit = DEFAULT) { return missing(items); }'
        row=locate(current,old,'.mjs')
        self.assertEqual(row['status'],'unique_symbol_reference')
        self.assertEqual(row['symbol'],'convert')
        self.assertEqual(row['source'],current)
        self.assertFalse(row['symbol_truncated'])

    def test_variable_to_function_shape_change_and_python(self):
        cases=[('function convert(x) { return x; }\n','const convert = y => y * 2;','.mjs'),
               ('def convert(x):\n    return x\n','def convert(y, mode=True):\n    return changed(y)\n','.py')]
        for source,old,suffix in cases:
            with self.subTest(suffix=suffix):self.assertEqual(locate(source,old,suffix)['source'],source)

    def test_duplicate_nested_missing_and_fake_comment_declarations_are_rejected(self):
        old='function convert(y) { return changed(y); }'
        for source in ['function convert(x) { return x; }\nfunction convert(z) { return z; }',
                       'function outer() { function convert(x) { return x; } }',
                       'function convert(x) { return x; } function outer() { function convert(x) {} }',
                       '// function convert(x) { return x; }\nconst sample=1;',
                       'const text = "function convert(x) { return x; }";', 'const other = 1;']:
            with self.subTest(source=source):self.assertIsNone(locate(source,old,'.mjs'))

    def test_parse_failure_and_unsupported_formats_do_not_guess(self):
        for source,old,suffix in [('function convert(', 'function convert(x) {}','.mjs'),
                                 ('function convert(x) {}','function convert(','.mjs'),
                                 ('function convert(x) {}','function convert(y) {}','.txt')]:
            self.assertIsNone(locate(source,old,suffix))

    def test_page_limit_and_exact_crlf_unicode_are_preserved(self):
        source='function convert(value) {\r\n'+('  // text 🎲\r\n'*100)+'  return value;\r\n}\r\n'
        row=locate(source,'function convert(x) { return changed(x); }','.mjs')
        self.assertEqual(len(row['source'].splitlines()),80)
        self.assertTrue(row['symbol_truncated']);self.assertTrue(row['more'])
        self.assertEqual(row['source'],''.join(source.splitlines(keepends=True)[:80]))
        huge='function convert(x) { return "'+'x'*10000+'"; }'
        self.assertIsNone(locate(huge,'function convert(y) { return y; }','.mjs'))

    def test_collect_keeps_scope_hash_bytes_and_original_file_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();path=root/'unit.mjs';state=root/'state.json'
            source='export function convert(value = 1) { return value; }\n';path.write_text(source)
            state.write_text(json.dumps({'before':{'root':str(root)},'task':{'files':['unit.mjs']}}))
            before=(path.read_bytes(),path.stat().st_mtime_ns)
            request={'path':'unit.mjs','old_texts':['function convert(item) { return wrong(item); }']}
            result=collect(root,state,request)
            self.assertTrue(result['readonly'])
            self.assertEqual(result['excerpts'][0]['source'],source)
            self.assertEqual(result['sha256'],hashlib.sha256(before[0]).hexdigest())
            self.assertLessEqual(encoded_size(result),12000)
            self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
            with self.assertRaisesRegex(ValueError,'scope'):collect(root,state,{**request,'path':'state.json'})


if __name__ == '__main__':
    unittest.main()
