"""Recovery compaction reconstructs native evidence and preserves frozen contracts."""
import json
from unittest.mock import patch
import unittest
from recovery_handoff import candidate
from replan_brief import separate_strategy
import test_recovery_report as report_tests


class HandoffTests(unittest.TestCase):
    def setUp(self):
        report_tests.ReportTests.setUp(self)
        self.launch.update(input_budget=57344,cloud=False)
        self.launch_path.write_text(json.dumps(self.launch))

    def test_real_packet_retains_exact_contract_and_does_not_reset_read_budget(self):
        audit={'bytes':800,'calls':[{'command':'read-file','paths':['sample.py'],'bytes':800}]}
        path=self.session/'recovery-source-reads.json';path.write_text(json.dumps(audit))
        before={p:p.read_bytes() for p in (self.path,path,self.session/'replan-evidence.json')}
        result=candidate(self.session);data=json.loads(result['summary'].split('\n',1)[1])
        request=data['task']['recovery_request']
        brief=json.loads(request.split('FAILURE EVIDENCE (project data):\n',1)[1].split('\n\nARCHITECTURE AND SHADOW:',1)[0])
        self.assertEqual(brief['failed_contract'],separate_strategy(self.packet['failed_todo'])[0])
        self.assertEqual(brief['previous_attempt_strategy'],separate_strategy(self.packet['failed_todo'])[1])
        self.assertEqual(data['source_read_budget']['calls_used'],1)
        self.assertEqual(data['source_read_budget']['bytes_used'],800)
        self.assertEqual(data['source_read_budget']['max_calls'],6)
        self.assertLessEqual(data['selection']['packet_estimated_tokens'],int(57344*.25))
        for p,raw in before.items():self.assertEqual(p.read_bytes(),raw)
        self.assertFalse(self.output.exists())

    def test_cloud_uses_cloud_budget_without_enlarging_failed_executor_contract(self):
        self.launch.update(input_budget=196608,cloud=True)
        self.launch_path.write_text(json.dumps(self.launch))
        data=json.loads(candidate(self.session)['summary'].split('\n',1)[1])
        self.assertEqual(data['selection']['provider'],'chatgpt')
        self.assertEqual(data['selection']['limits']['packet'],int(196608*.25))
        self.assertIn(str(self.packet['failed_todo']['context']['max_input_tokens']),
                      data['task']['recovery_request'])

    def test_stale_source_and_changed_plan_stop_before_handoff(self):
        changed=self.root/'unexpected.py';changed.write_text('x=1\n')
        with self.assertRaisesRegex(ValueError,'stale'):candidate(self.session)
        changed.unlink();self.path.write_text(json.dumps({**self.plan,'goal':'changed'}))
        with self.assertRaisesRegex(ValueError,'plan changed'):candidate(self.session)

    def test_oversized_contract_does_not_fall_back_to_model_summary(self):
        with patch('recovery_handoff.build',side_effect=ValueError('contract exceeds budget')):
            with self.assertRaisesRegex(ValueError,'exceeds budget'):candidate(self.session)
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
