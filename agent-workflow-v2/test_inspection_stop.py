"""Batch inspection must expose budget and provider aborts despite Pi exit zero."""
import json
from pathlib import Path
import tempfile
import unittest
from inspection_stop import completion


class InspectionCompletion(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.session=Path(self.temp.name)

    def timing(self, *stops):
        (self.session/'provider-timing.jsonl').write_text('\n'.join(json.dumps(
            {'type':'request_end','stop_reason':stop,'error':'Request aborted' if stop=='aborted' else None})
            for stop in stops)+'\n')

    def test_budget_abort_is_nonzero_and_explains_cap(self):
        (self.session/'request-budget-result.json').write_text(json.dumps(
            {'passed':False,'admission_tokens':33398,'limit':32768}))
        self.timing('toolUse','aborted')
        code,reason=completion(0,self.session)
        self.assertEqual(code,24)
        self.assertIn('33398',reason);self.assertIn('32768',reason)
        self.assertIn('request-budget-result.json',reason)

    def test_provider_abort_and_unfinished_tools_are_not_completion(self):
        for stop in ['aborted','error','toolUse']:
            self.timing(stop)
            code,reason=completion(0,self.session)
            self.assertEqual(code,1);self.assertIn('completed answer',reason)

    def test_tools_followed_by_final_answer_pass(self):
        self.timing('toolUse','stop')
        self.assertEqual(completion(0,self.session),(0,''))

    def test_original_process_failure_is_preserved(self):
        self.assertEqual(completion(124,self.session),(124,''))

    def test_absent_optional_timing_does_not_invent_provider_failure(self):
        self.assertEqual(completion(0,self.session),(0,''))
