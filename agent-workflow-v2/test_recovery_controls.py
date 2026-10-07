"""Recovery sees inherited caps and honest telemetry, never the full launch command."""
import json
import unittest
from recovery_controls import summarize


class ControlTests(unittest.TestCase):
    def test_effective_limits_and_completed_guard_counts_are_preserved(self):
        launch={'effective_settings':{'context':98304,'input_tokens':32768,'output_tokens':16384,
            'thinking':'on','reasoning':'xhigh','reasoning_budget':2048,'profile':'quality'},
            'command':['PRIVATE_IMPLEMENTATION'],'prompt':'PRIVATE_PROMPT'}
        rows=[{'thinking_guard':{'budget_tokens':2048,'engaged':'budget'}},
              {'thinking_guard':{'budget_tokens':2048,'engaged':None}},
              {'request_cancelled':True,'thinking_guard':{'budget_tokens':1024,'engaged':'budget'}},{}]
        value=summarize(launch,{'native_requests':rows})
        self.assertEqual(value['effective_executor_controls'],launch['effective_settings'])
        observed=value['thinking_guard_observations']
        self.assertEqual(observed['completed_requests'],3)
        self.assertEqual(observed['requests_with_guard_telemetry'],2)
        self.assertEqual(observed['budget_hits'],1)
        self.assertEqual(observed['reported_budget_tokens'],[2048])
        self.assertNotIn('PRIVATE_',json.dumps(value))

    def test_unknown_telemetry_does_not_claim_cap_was_disabled(self):
        value=summarize({}, {'native_requests':[{'thinking_guard':None}]})
        self.assertEqual(value['effective_executor_controls'],{})
        self.assertEqual(value['thinking_guard_observations']['requests_with_guard_telemetry'],0)
        self.assertIn('unknown',value['thinking_guard_observations']['note'])
