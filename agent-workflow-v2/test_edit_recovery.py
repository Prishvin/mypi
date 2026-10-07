"""Read-only edit diagnostics for unnamed blocks, bounds and frozen scope."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from edit_recovery import collect, current_span, encoded_size


class EditRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.root = base / 'project'
        self.root.mkdir()
        self.path = self.root / 'checks.mjs'
        self.state = base / 'state.json'
        self.contract = {'before': {'root': str(self.root)}, 'task': {'files': ['checks.mjs']}}
        self.state.write_text(json.dumps(self.contract))
        self.source = 'test("bounded example", () => {\n  const sample = 42;\n  assert.equal(sample, 42);\n});\n'
        self.path.write_text(self.source)

    def evidence(self, old=None, **changes):
        request = {'path': 'checks.mjs', 'old_texts': [old or self.source.replace('= 42', '= 41')]}
        return collect(self.root, self.state, {**request, **changes})

    def test_test_callback_returns_current_exact_text_not_guessed_patch(self):
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        result = self.evidence()
        row = result['excerpts'][0]
        self.assertEqual(row['status'], 'unique_line_anchor')
        self.assertEqual(row['source'], self.source)
        self.assertEqual(row['anchor_line'], 1)
        self.assertEqual(result['sha256'], hashlib.sha256(before[0]).hexdigest())
        self.assertTrue(result['readonly'])
        self.assertEqual(before, (self.path.read_bytes(), self.path.stat().st_mtime_ns))

    def test_arrow_functions_and_constants_need_no_function_declaration(self):
        for source in ['const convertValue = x => x + 1;\nconst bound = 10;\n',
                       'const settings = {\n  timeout: 10,\n};\n']:
            with self.subTest(source=source):
                self.path.write_text(source)
                self.assertEqual(self.evidence(source.replace('10', '11'))['excerpts'][0]['source'], source)

    def test_missing_opening_line_uses_a_unique_inner_anchor(self):
        old = self.source.replace('bounded example', 'old title').replace('sample = 42', 'sample = 41')
        row = self.evidence(old)['excerpts'][0]
        self.assertEqual(row['anchor_line'], 3)
        self.assertEqual(row['source'], self.source)

    def test_ambiguous_and_punctuation_anchors_do_not_guess(self):
        text = 'const identical = 42;\n});\n' * 3
        for old in ['const identical = 42;\nchanged\n', '});\nchanged\n', 'not present anywhere']:
            result = current_span(text, old)
            self.assertEqual(result['status'], 'no_unique_anchor')
            self.assertNotIn('source', result)

    def test_valid_batch_members_report_exact_occurrences_without_repetition(self):
        self.path.write_text(self.source * 2)
        result = self.evidence(old_texts=['const sample = 42;', 'invented text'])
        self.assertEqual(result['excerpts'][0], {'edit_index': 0, 'status': 'old_text_present', 'occurrences': 2})
        self.assertEqual(result['excerpts'][1]['status'], 'no_unique_anchor')

    def test_crlf_unicode_no_final_newline_and_literal_line_labels_are_preserved(self):
        raw = 'test("emoji 🎲", () => {\r\n  // 123: literal label\r\n  const answer = "é";\r\n});'.encode()
        self.path.write_bytes(raw)
        result = self.evidence(raw.decode().replace('"é"', '"è"'))
        self.assertEqual(result['excerpts'][0]['source'].encode(), raw)
        self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())

    def test_changed_file_returns_new_snapshot_not_cached_text(self):
        first = self.evidence()
        self.path.write_text(self.source.replace('42', '43'))
        second = self.evidence()
        self.assertNotEqual(first['sha256'], second['sha256'])
        self.assertIn('43', second['excerpts'][0]['source'])

    def test_deep_anchor_returns_bounded_page_with_absolute_offsets(self):
        prefix = 'const padding = 0;\n' * 200
        self.path.write_text(prefix + self.source + 'const later = 0;\n' * 200)
        row = self.evidence()['excerpts'][0]
        self.assertEqual(row['start_line'], 201)
        self.assertNotIn('padding', row['source'])
        self.assertTrue(row['more'])
        self.assertEqual(row['next_offset'], row['end_line'])
        self.assertLessEqual(len(row['source'].splitlines()), 80)

    def test_long_and_escaped_lines_obey_serialized_response_budget(self):
        text = 'const uniqueAnchor = 1;\n' + ('\\"🎲' * 300 + '\n') * 90
        self.path.write_text(text)
        old = 'const uniqueAnchor = 1;\n' + ('wrong\n' * 100)
        result = self.evidence(old_texts=[old] * 8)
        self.assertLessEqual(encoded_size(result), 12000)
        self.assertGreater(result['omitted_edits'], 0)
        self.assertIn('source', result['excerpts'][0])
        self.assertTrue(result['excerpts'][0]['more'])

    def test_oversized_single_anchor_line_does_not_dump_source(self):
        line = 'const huge = "' + 'x' * 15000 + '";'
        self.path.write_text(line + '\nconst value = 1;')
        result = self.evidence(line + '\nmissing')
        self.assertEqual(result['excerpts'][0]['status'], 'no_unique_anchor')
        self.assertLess(encoded_size(result), 1000)

    def test_scope_root_traversal_and_symlink_escape_rejected(self):
        other = self.root / 'secret.mjs'
        other.write_text('private')
        for name in ['secret.mjs', '../state.json']:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'scope'):
                self.evidence(path=name)
        self.path.unlink()
        self.path.symlink_to(self.state)
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.evidence()
        with self.assertRaisesRegex(ValueError, 'root'):
            collect(self.root.parent, self.state, {'path': 'checks.mjs', 'old_texts': ['x']})

    def test_invalid_request_and_nontext_file_rejected(self):
        for changes in [{'old_texts': []}, {'old_texts': ['']}, {'old_texts': [None]},
                        {'old_texts': ['x'] * 9}, {'old_texts': ['x' * 65537]}, {'path': ''}]:
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                self.evidence(**changes)
        for raw in [b'\xff', b'abc\x00def', b'x' * 1048577]:
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.evidence()
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.evidence()

    def test_cli_failures_are_bounded_structured_errors(self):
        request = self.state.parent / 'request.json'
        for data in ['[]', '{', 'x' * 65537]:
            request.write_text(data)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('edit_recovery.py')),
                                     '--root', str(self.root), '--state', str(self.state), '--input', str(request)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('error', json.loads(result.stdout))
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
