"""Failure review receives selected test setup, never application bodies or unrelated files."""
import json
from pathlib import Path
import tempfile
import unittest

from failure_test_context import collect


class FailingTestContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root, self.session = self.base / 'project', self.base / 'session'
        self.root.mkdir(); self.session.mkdir(); (self.root / 'test').mkdir()
        self.test = self.root / 'test/units.test.mjs'
        self.test.write_text('const LIMIT = 7;\nconst UNRELATED = "SECRET_VALUE";\n'
                             'test("boundary", () => {\n  const input = LIMIT + 1;\n  assert.equal(parse(input), 8);\n});\n'
                             'test("other", () => { return "UNRELATED_TEST_BODY"; });\n')
        (self.root / 'app.mjs').write_text('export function parse(x) { return "PRIVATE_APPLICATION_BODY"; }')
        self.task = {'id': 'T1', 'files': ['app.mjs', 'test/units.test.mjs'],
                     'tests': [['node', '--test', 'test/units.test.mjs']]}
        self.log = self.session / 'task-state-test-0.log'
        self.log.write_text('test at test/units.test.mjs:3:1\n'
                            f'  at TestContext.<anonymous> (file://{self.test}:5:10)\n'
                            f'  at parse (file://{self.root}/app.mjs:1:20)\n')
        self.state = {'before': {'root': str(self.root)}, 'task': self.task,
                      'evidence': {'results': [{'log': str(self.log), 'exit_code': 1}]}}
        self.packet = {'session': str(self.session), 'failed_todo': self.task}
        self.save()

    def save(self):
        (self.session / 'task-state.json').write_text(json.dumps(self.state))

    def test_js_selected_case_and_referenced_literal_only(self):
        data = collect(self.root, self.packet)
        self.assertEqual([r['path'] for r in data['files']], ['test/units.test.mjs'])
        case = data['files'][0]
        self.assertEqual(len(case['spans']), 1)
        self.assertIn('const input = LIMIT + 1', str(case))
        self.assertEqual(case['referenced_primitive_literals'], ['const LIMIT = 7;'])
        self.assertNotIn('PRIVATE_APPLICATION_BODY', str(data))
        self.assertNotIn('UNRELATED_TEST_BODY', str(data))
        self.assertNotIn('SECRET_VALUE', str(data))

    def test_python_traceback_selects_exact_test_method(self):
        path = self.root / 'test_values.py'
        path.write_text('LIMIT = 7\nclass TestNumbers:\n    def test_boundary(self):\n        assert parse(LIMIT) == 7\n\n    def test_other(self):\n        assert "UNRELATED_TEST_BODY"\n')
        self.task['files'].append('test_values.py'); self.save()
        self.log.write_text(f'  File "{path}", line 4, in test_boundary\nAssertionError\n')
        data = collect(self.root, self.packet)
        self.assertEqual(data['files'][0]['spans'][0]['start_line'], 3)
        self.assertIn('LIMIT = 7', str(data))
        self.assertNotIn('UNRELATED_TEST_BODY', str(data))

    def test_referenced_fixture_array_and_test_helper_are_available_without_other_code(self):
        self.test.write_text('const BASE = ["AB", "CD"];\nconst ROWS = BASE;\n'
                             'function gridFor(rows) { return fakeGrid(rows); }\n'
                             'function unrelated() { return "UNRELATED_TEST_BODY"; }\n'
                             'test("boundary", () => {\n  const grid = gridFor(ROWS);\n  assert.equal(grid.at(0,0), "A");\n});\n')
        self.log.write_text(f'  at TestContext.<anonymous> (file://{self.test}:7:10)\n')
        data = collect(self.root, self.packet)
        setup = data['files'][0]['referenced_test_setup']
        self.assertEqual({d['name'] for d in setup['definitions']}, {'BASE', 'ROWS', 'gridFor'})
        self.assertIn('"AB", "CD"', str(setup))
        self.assertNotIn('UNRELATED_TEST_BODY', str(data))
        self.assertNotIn('PRIVATE_APPLICATION_BODY', str(data))

    def test_oversized_fixture_is_explicitly_omitted_instead_of_partially_copied(self):
        self.test.write_text('const ROWS = [\n' + '"abc",\n'*50 + '];\n'
                             'test("boundary", () => { assert.ok(ROWS); });\n')
        self.log.write_text('test at test/units.test.mjs:53:1\n')
        setup = collect(self.root, self.packet)['files'][0]['referenced_test_setup']
        self.assertFalse(setup['definitions']); self.assertIn('ROWS', setup['omitted'])

    def test_mismatched_root_or_task_binding_yields_no_source(self):
        self.state['before']['root'] = str(self.base / 'wrong'); self.save()
        data = collect(self.root, self.packet)
        self.assertFalse(data['files']); self.assertTrue(data['omitted'])
        self.state['before']['root'] = str(self.root)
        self.state['task'] = {**self.task, 'id': 'OTHER'}; self.save()
        self.assertFalse(collect(self.root, self.packet)['files'])

    def test_unrecorded_external_logs_and_symlinked_test_source_are_excluded(self):
        other = self.base / 'outside.log'; other.write_bytes(self.log.read_bytes())
        self.state['evidence']['results'][0]['log'] = str(other); self.save()
        self.assertFalse(collect(self.root, self.packet)['files'])
        self.state['evidence']['results'][0]['log'] = str(self.log); self.save()
        outside = self.base / 'outside.mjs'; outside.write_text('PRIVATE_OUTSIDE')
        self.test.unlink(); self.test.symlink_to(outside)
        self.assertFalse(collect(self.root, self.packet)['files'])

    def test_passing_logs_and_unknown_line_numbers_do_not_select_source(self):
        self.state['evidence']['results'][0]['exit_code'] = 0; self.save()
        self.assertFalse(collect(self.root, self.packet)['files'])
        self.state['evidence']['results'][0]['exit_code'] = 1; self.save()
        self.log.write_text('test at test/units.test.mjs:9000:1\n')
        self.assertFalse(collect(self.root, self.packet)['files'])
        self.log.write_text('test at not-the-project/test/units.test.mjs:5:10\n')
        self.assertFalse(collect(self.root, self.packet)['files'])

    def test_size_limit_marks_omission_without_dropping_acceptance(self):
        data = collect(self.root, self.packet, max_bytes=512)
        self.assertLessEqual(len(json.dumps(data).encode()), 512)
        self.assertFalse(data['files']); self.assertTrue(data['omitted'])
        with self.assertRaises(ValueError): collect(self.root, self.packet, max_bytes=10)

    def test_no_session_adds_no_source_and_files_are_never_mutated(self):
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in [self.test, self.log]}
        self.assertFalse(collect(self.root, {'failed_todo': self.task})['files'])
        collect(self.root, self.packet)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_real_review_packet_contains_test_evidence_but_no_application_body(self):
        from failure_context import build
        from project_map import scan
        self.task['context'] = {'max_input_tokens': 32768, 'window_tokens': 65536}
        self.save()
        plan = self.base / 'plan.json'; plan.write_text(json.dumps({'tasks': [self.task]}))
        packet = {**self.packet, 'plan': str(plan), 'project': str(self.root),
                  'current_snapshot': scan(self.root, ['.'])['snapshot'],
                  'remaining': [self.task], 'completed': [], 'metrics': {}}
        prompt, info = build(self.root, packet, 'qwen')
        self.assertIn('selected_failing_test_evidence', prompt)
        self.assertIn('const input = LIMIT + 1', prompt)
        self.assertNotIn('PRIVATE_APPLICATION_BODY', prompt)
        self.assertNotIn('UNRELATED_TEST_BODY', prompt)
        self.assertLessEqual(info['packet_estimated_tokens'], info['limits']['packet'])


if __name__ == '__main__':
    unittest.main()
