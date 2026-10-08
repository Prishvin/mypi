"""Prevent cross-test mixing of causes and assertion values in bounded evidence."""
import json
import unittest
from failure_diagnostics import summarize
from failure_cases import grouped


class FailureCaseTests(unittest.TestCase):
    def test_node_cases_keep_shared_expected_and_different_actual_values(self):
        log='\n'.join(['✖ first (1ms)','✖ second (2ms)','ℹ tests 2','ℹ fail 2',
            '✖ failing tests:','test at test.mjs:1:1','✖ first (1ms)',
            '  AssertionError [ERR_ASSERTION]: count mismatch',
            '    actual: 0,','    expected: 1,',"    operator: 'strictEqual',",
            'test at test.mjs:9:1','✖ second (2ms)',
            '  AssertionError [ERR_ASSERTION]: count mismatch',
            '    actual: 6,','    expected: 1,',"    operator: 'strictEqual',"])
        value=summarize(log);a,b=value['failure_cases']
        self.assertEqual((a['test'],a['actual'],a['expected']),('first','0','1'))
        self.assertEqual((b['test'],b['actual'],b['expected']),('second','6','1'))
        self.assertEqual(a['causes'],b['causes'])
        self.assertEqual(len(value['failure_cases']),2)

    def test_ansi_python_and_tap_reporters_retain_reported_strings(self):
        python='FAIL: test_value (unit.T)\nTraceback (most recent call last):\nAssertionError: 1 != 2\nRan 1 test in 0.1s'
        self.assertEqual(summarize(python)['failure_cases'][0]['test'],'test_value (unit.T)')
        tap="\x1b[31mnot ok 1 - example\x1b[0m\nerror: mismatch\nexpected: 2\nactual: 1\n# tests 1"
        case=summarize(tap)['failure_cases'][0]
        self.assertEqual((case['test'],case['actual'],case['expected']),('example','1','2'))
        self.assertNotIn('\x1b',str(case))

    def test_overview_or_stack_source_cannot_create_a_case_without_cause(self):
        self.assertEqual(summarize('✖ case (1ms)\nℹ fail 1\nactual: 4')['failure_cases'],[])
        case=summarize('✖ case (1ms)\nTypeError: wrong value\nat private (secret.mjs:4)\nPRIVATE_BODY();')['failure_cases'][0]
        self.assertNotIn('PRIVATE',str(case));self.assertNotIn('secret.mjs',str(case))
        self.assertNotIn('actual',case)

    def test_partial_complex_fields_are_marked_and_never_evaluated(self):
        log='✖ case\nAssertionError: mismatch\nactual: {\nsecret: 2\n}\nexpected: '+ 'x'*200
        case=summarize(log)['failure_cases'][0]
        self.assertEqual(case['actual'],'{')
        self.assertEqual(case['partial_fields'],['actual','expected'])
        self.assertEqual(len(case['expected']),160)
        self.assertNotIn('secret',str(case))

    def test_many_large_cases_are_omitted_whole_with_a_byte_bound(self):
        lines=[]
        for i in range(20):lines += ['✖ '+str(i)+'界'*300,'Error: '+'界'*400,'actual: '+'界'*200]
        cases,omitted=grouped(lines)
        self.assertLessEqual(len(json.dumps(cases,ensure_ascii=False).encode()),6000)
        self.assertEqual(len(cases)+omitted,20)
        self.assertTrue(cases[0]['name_truncated']);self.assertTrue(cases[0]['cause_truncated'])
        self.assertEqual(cases[0]['partial_fields'],['actual'])

    def test_case_count_and_multiple_causes_are_explicitly_bounded(self):
        lines=[]
        for i in range(20):lines += [f'✖ test {i}','Error: one','Error: two','Error: three']
        cases,omitted=grouped(lines)
        self.assertEqual((len(cases),omitted),(8,12))
        self.assertEqual(cases[0]['causes'],['Error: one','Error: two'])
        self.assertEqual(cases[0]['omitted_causes'],1)
