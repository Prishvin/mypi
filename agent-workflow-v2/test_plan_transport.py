"""Transport compatibility preserves contracts and rejects damaged/ambiguous JSON."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from plan_transport import task_list
from plan_shape import canonical
from plans import save
from test_plans import example_task


class TransportTests(unittest.TestCase):
    def test_plain_and_encoded_preserve_every_field_without_mutating_input(self):
        tasks = [example_task(), {**example_task('T2'), 'depends_on': ['T1']}]
        for value in (tasks, json.dumps(tasks, ensure_ascii=False)):
            raw = {'goal': 'Build', 'architecture': 'Pure functions', 'tasks': value}
            before = copy.deepcopy(raw)
            result = canonical(raw)
            self.assertEqual(result['tasks'], tasks)
            self.assertEqual(raw, before)
            self.assertEqual(bool(result.get('schema_normalization')), isinstance(value, str))

    def test_observed_missing_key_delimiter_has_bounded_actionable_error(self):
        value = '[{"id":"T14","depends_on ["T05"],"description":"' + 'x' * 60000 + '"}]'
        with self.assertRaises(ValueError) as caught:
            task_list(value)
        message = str(caught.exception)
        self.assertIn('malformed JSON at character', message)
        self.assertIn('depends_on', message)
        self.assertIn('original proposal is retained', message)
        self.assertLess(len(message), 600)

    def test_rejects_wrong_shapes_duplicate_keys_nonfinite_and_truncated_json(self):
        for value in ([], {}, None, 1, '[]', '{}', '[null]', '[1]', '["{}"]',
                      '"[]"', '[{"id":"A","id":"B"}]', '[{"x":NaN}]',
                      '[{"x":Infinity}]', '[{"id":"A"}', '[] trailing'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                task_list(value)

    def test_limits_utf8_bytes_and_nesting(self):
        for value in ('[{"x":"' + 'é' * 524288 + '"}]', '[' * 1100 + '0' + ']' * 1100):
            with self.assertRaises(ValueError):
                task_list(value)

    def test_native_store_accepts_encoded_array_but_still_enforces_all_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base / 'project'; root.mkdir()
            task = example_task()
            raw = {'goal': 'Build', 'architecture': 'Pure functions', 'tasks': json.dumps([task])}
            result = save(root, ['.'], raw, base / 'good.json')
            self.assertEqual(result['todos'], 1)
            stored = json.loads((base / 'good.json').read_text())
            self.assertEqual(stored['tasks'][0]['tests'], task['tests'])
            task['coverage'] = []
            raw['tasks'] = json.dumps([task])
            with self.assertRaisesRegex(ValueError, 'Every acceptance'):
                save(root, ['.'], raw, base / 'bad.json')
            self.assertFalse((base / 'bad.json').exists())


if __name__ == '__main__':
    unittest.main()
