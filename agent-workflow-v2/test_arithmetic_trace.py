"""Exercise the installed native skill, preparation binding and bounded arithmetic."""
import json
from pathlib import Path
import tempfile
import unittest
from jsonschema import ValidationError
from skill_runner import prepare, run
from workflow_skills import instructions


class ArithmeticTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        prepare(self.session, 'arithmetic-trace', 'code')

    def trace(self, initial, operations, **kwargs):
        return run(self.session, 'arithmetic-trace', dict(initial=initial, operations=operations, **kwargs), 'code')['data']

    def test_measures_precision_and_tiny_residual_without_rounding_it_away(self):
        data = self.trace(.3, [{'op': 'subtract', 'value': .1}], repeat=3)
        self.assertLess(data['final']['value'], 0)
        self.assertNotEqual(data['final']['value'], 0)
        self.assertEqual(data['final']['sign'], -1)
        self.assertEqual(len(data['results']), 3)
        self.assertFalse(data['application_executed'])
        self.assertEqual(data['results'][0]['precision17'], '0.19999999999999998')

    def test_all_operations_and_order_are_native_and_repeatable(self):
        ops = [{'op': name, 'value': value} for name, value in
               [('add', 4), ('multiply', 3), ('subtract', 1), ('divide', 2), ('min', 9), ('max', 10)]]
        data = self.trace(2, ops)
        self.assertEqual([x['value'] for x in data['results']], [6, 18, 17, 8.5, 8.5, 10])
        data = self.trace(2, [{'op': 'multiply', 'value': 2}], repeat=3)
        self.assertEqual([x['value'] for x in data['results']], [4, 8, 16])

    def test_zero_sign_is_explicit(self):
        data = self.trace(0, [{'op': 'multiply', 'value': -1}])
        self.assertEqual(data['final']['sign'], 0)
        self.assertTrue(data['final']['negative_zero'])

    def test_nonfinite_intermediates_and_excess_work_fail_visibly(self):
        for initial, ops, kwargs in [(1, [{'op': 'divide', 'value': 0}], {}),
                                      (1e100, [{'op': 'multiply', 'value': 2}], {}),
                                      (0, [{'op': 'add', 'value': 1}]*8, {'repeat': 5})]:
            with self.subTest(initial=initial, kwargs=kwargs), self.assertRaises(ValueError):
                self.trace(initial, ops, **kwargs)
        self.assertEqual(len(list((self.session/'skill-runs').glob('*/failure.json'))), 3)

    def test_code_paths_unknown_operations_and_non_numeric_input_are_rejected(self):
        for payload in [dict(initial=1, operations=[{'op': 'eval', 'value': 1}]),
                        dict(initial='process.exit()', operations=[{'op': 'add', 'value': 1}]),
                        dict(initial=1, operations=[{'op': 'add', 'value': 1}], project='/tmp')]:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                run(self.session, 'arithmetic-trace', payload, 'code')

    def test_results_are_small_and_artifacts_stay_in_session(self):
        data = self.trace(1, [{'op': 'divide', 'value': 3}], repeat=32)
        self.assertLess(len(json.dumps(data)), 8192)
        self.assertEqual(len(data['results']), 32)
        self.assertTrue(list((self.session/'skill-runs').glob('*/result.json')))
        self.assertIn('arithmetic-trace', instructions(Path(__file__).resolve().parent, 'code'))


if __name__ == '__main__':
    unittest.main()
