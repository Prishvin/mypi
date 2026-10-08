"""Bounded automatic recovery, durable escalation and measured prototype-only context."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import plans
from project_map import scan
from runner_process import read,save
from recovery_runner import execute
from failure_context import build
from test_coverage_plan import draft


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'project';self.root.mkdir()
        (self.root/'one.py').write_text('def normalize(text):\n    """Normalize an input."""\n    return "PRIVATE_BODY_SENTINEL"\n')
        (self.root/'architecture.md').write_text('# Normalization\n`one.py` owns normalize(text).\n')
        self.path=self.base/'plan.json';plans.save(self.root,['.'],draft(),self.path)
        self.folder=self.base/'run-1';self.folder.mkdir();self.runs=[];self.reviews=[];self.codes=[20,0]

    def packet(self,path):
        data=read(path)
        return {'project':str(self.root),'plan':str(path),'goal':data['goal'],
            'current_snapshot':scan(self.root,['.'])['snapshot'],'failed_todo':data['tasks'][0],
            'remaining':data['tasks'],'completed':[],'metrics':{},'reason':'acceptance_failed',
            'failed_tests':[{'observations':['not ok 1 - empty input','error: wrong result']}],
            'acceptance_fixtures':{}}

    def runner(self,root,path,folder,*,resume=False):
        self.runs.append((path,folder,resume));folder.mkdir(parents=True,exist_ok=True)
        code=self.codes.pop(0)
        if code==20:save(folder/'replan-request.json',self.packet(path))
        return code

    def reviewer(self,root,evidence,output,provider,timeout):
        from planning_service import attach_lineage
        self.reviews.append(evidence);packet=read(evidence);data=copy.deepcopy(read(Path(packet['plan'])))
        data['failure_analysis']='Observed assertion mismatch; repair normalization boundary logic and rerun frozen tests.'
        attach_lineage(data,packet);plans.save(root,['.'],data,output)
        return {'passed':True,'plan':str(output)}

    def run_flow(self,resume=False,retry_review=False,allow_repair=False):
        with patch('role_selection.load',return_value={'planner':'qwen'}):
            return execute(self.root,self.path,self.folder,resume=resume,executor=self.runner,reviewer=self.reviewer,retry_review=retry_review,allow_repair=allow_repair)

    def test_standalone_review_publishes_bound_running_and_completed_stages(self):
        from recovery_runner import review
        destination=self.base/'standalone.json';evidence=self.base/'evidence.json'
        save(evidence,self.packet(self.path));folder=destination.with_suffix('.stages')
        def create(*args):
            state=read(folder/'state.json')
            self.assertEqual(state['status'],'running')
            self.assertEqual(state['recovery_evidence'],str(evidence))
            return {'passed':True,'plan':str(destination)}
        with patch('planning_service.create_draft',side_effect=create):
            self.assertTrue(review(self.root,evidence,destination,'qwen',1200)['passed'])
        self.assertEqual(read(folder/'state.json')['status'],'complete')
        self.assertEqual(read(folder/'queue.json')['tasks'][0]['status'],'done')
        before=(folder/'state.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'new review destination'):
            review(self.root,evidence,destination,'qwen',1200)
        self.assertEqual((folder/'state.json').read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'outside'):
            review(self.root,evidence,self.root/'bad.json','qwen',1200)
        interrupted=self.base/'interrupted.json'
        with patch('planning_service.create_draft',side_effect=RuntimeError('fixture stop')):
            with self.assertRaisesRegex(RuntimeError,'fixture stop'):
                review(self.root,evidence,interrupted,'qwen',1200)
        self.assertEqual(read(interrupted.with_suffix('.stages')/'state.json')['status'],'interrupted')

    def test_explicit_continuation_grants_only_one_further_repair_and_preserves_history(self):
        self.codes=[20,20];self.assertEqual(self.run_flow()['code'],20)
        before=read(self.folder/'recovery-state.json')
        self.codes=[20];self.assertEqual(self.run_flow(allow_repair=True)['code'],20)
        after=read(self.folder/'recovery-state.json')
        self.assertEqual(after['spent_ids'],before['spent_ids']);self.assertEqual(after['spent_cases'],before['spent_cases'])
        self.assertEqual(len(after['repair_authorizations']),1)
        self.assertEqual(len(self.runs),3);self.assertEqual(len(self.reviews),2)
        self.assertEqual(self.run_flow(resume=True)['code'],20)
        self.assertEqual(len(self.runs),3);self.assertEqual(len(self.reviews),2)

    def test_explicit_continuation_can_complete_without_replaying_failed_execution_first(self):
        self.codes=[20,20];self.run_flow();self.codes=[0]
        result=self.run_flow(allow_repair=True)
        self.assertEqual(result['code'],0);self.assertEqual(result['plan'].name,'repair-2.json')
        self.assertEqual(len(self.runs),3);self.assertEqual(len(self.reviews),2)

    def test_continuation_rejects_stale_mismatched_and_nonexecuted_evidence(self):
        with self.assertRaisesRegex(ValueError,'stopped corrective'):self.run_flow(allow_repair=True)
        with patch.object(self,'reviewer',return_value={'passed':False}):self.run_flow()
        with self.assertRaisesRegex(ValueError,'retry-review'):self.run_flow(allow_repair=True)
        self.codes=[20];self.run_flow(retry_review=True)
        checkpoint=read(self.folder/'recovery-state.json');packet_path=Path(checkpoint['current_run'])/'replan-request.json'
        packet=read(packet_path);packet['failed_todo']['id']='different';save(packet_path,packet)
        with self.assertRaisesRegex(ValueError,'differs'):self.run_flow(allow_repair=True)
        packet['failed_todo']['id']=checkpoint['repairs'][-1]['todo'];save(packet_path,packet)
        (self.root/'one.py').write_text('changed=1\n')
        with self.assertRaisesRegex(ValueError,'stale'):self.run_flow(allow_repair=True)
        self.assertEqual(len(self.runs),2)

    def test_explicit_review_retry_preserves_allowance_and_does_not_repeat_failed_execution(self):
        with patch.object(self,'reviewer',return_value={'passed':False,'exit_code':124}):
            self.assertEqual(self.run_flow()['code'],20)
        before=read(self.folder/'recovery-state.json')
        result=self.run_flow(retry_review=True)
        self.assertEqual(result['code'],0);self.assertEqual(len(self.runs),2)
        state=read(self.folder/'recovery-state.json')
        self.assertEqual(state['spent_ids'],before['spent_ids']);self.assertEqual(state['spent_cases'],before['spent_cases'])
        self.assertNotIn('reason',state)
        self.assertEqual(result['plan'].name,'repair-2.json')
        self.assertEqual(len(state['review_retry_authorizations']),1)
        self.assertEqual(state['repairs'][0]['review_result']['exit_code'],124)

    def test_review_retry_does_not_grant_another_repair_after_corrective_execution_fails(self):
        self.codes=[20,20]
        with patch.object(self,'reviewer',return_value={'passed':False,'exit_code':124}):self.run_flow()
        self.assertEqual(self.run_flow(retry_review=True)['code'],20)
        self.assertEqual(len(self.reviews),1)
        with self.assertRaisesRegex(ValueError,'generated plan'):self.run_flow(retry_review=True)
        self.assertEqual(len(self.runs),2)

    def test_review_retry_rejects_stale_source_and_normal_execution(self):
        with self.assertRaisesRegex(ValueError,'stopped failure review'):self.run_flow(retry_review=True)
        with patch.object(self,'reviewer',return_value={'passed':False,'exit_code':124}):self.run_flow()
        (self.root/'one.py').write_text('x=2\n')
        with self.assertRaisesRegex(ValueError,'stale'):self.run_flow(retry_review=True)
        self.assertEqual(len(self.runs),1)

    def test_one_review_then_one_repair_success_returns_actual_final_target(self):
        result=self.run_flow();self.assertEqual(result['code'],0)
        self.assertEqual(len(self.reviews),1);self.assertEqual(len(self.runs),2)
        self.assertEqual(result['plan'].name,'repair-1.json');self.assertEqual(result['run_dir'].name,'repair-1')
        self.assertEqual(read(self.folder/'execution-target.json')['plan'],str(result['plan']))

    def test_consecutive_failure_asks_user_and_rerun_cannot_reset_allowance(self):
        self.codes=[20,20];result=self.run_flow();self.assertEqual(result['code'],20)
        self.assertIn('automatic repair',result['question']['question'])
        self.assertEqual(self.run_flow(resume=True)['code'],20)
        self.assertEqual(len(self.runs),2);self.assertEqual(len(self.reviews),1)

    def test_invalid_review_does_not_start_another_worker(self):
        with patch.object(self,'reviewer',return_value={'passed':False}):result=self.run_flow()
        self.assertEqual(result['code'],20);self.assertEqual(len(self.runs),1)

    def test_scheduler_exception_preserves_saved_review_and_allowance_for_explicit_resume(self):
        original=self.runner
        def crashed(*args,**kwargs):
            code=original(*args,**kwargs)
            if len(self.runs)==2:raise RuntimeError('scheduler fixture failed before worker launch')
            return code
        with patch.object(self,'runner',side_effect=crashed):
            with self.assertRaisesRegex(RuntimeError,'scheduler fixture'):self.run_flow()
        state=read(self.folder/'recovery-state.json')
        self.assertEqual(state['status'],'interrupted');self.assertEqual(len(self.reviews),1)
        self.assertTrue(Path(state['current_plan']).is_file())
        self.assertEqual(read(self.folder/'coordinator-error.json')['type'],'RuntimeError')
        self.codes=[0];self.assertEqual(self.run_flow(resume=True)['code'],0)
        self.assertEqual(len(self.reviews),1)
        after=read(self.folder/'recovery-state.json')
        self.assertEqual(after['spent_ids'],state['spent_ids'])
        self.assertEqual(after['spent_cases'],state['spent_cases'])

    def test_interrupted_repair_resumes_same_contract_without_new_review(self):
        self.codes=[20,130];result=self.run_flow();self.assertEqual(result['code'],130)
        self.codes=[0];self.assertEqual(self.run_flow(resume=True)['code'],0)
        self.assertTrue(self.runs[-1][-1]);self.assertEqual(len(self.reviews),1)

    def test_interrupted_failure_review_requires_user_instead_of_repeated_requests(self):
        with patch.object(self,'reviewer',side_effect=KeyboardInterrupt()):self.assertEqual(self.run_flow()['code'],130)
        self.assertEqual(self.run_flow(resume=True)['code'],20);self.assertEqual(len(self.runs),1)

    def test_fresh_failure_in_different_task_gets_its_own_one_attempt(self):
        original=self.runner
        def fail_next(root,path,folder,*,resume=False):
            code=original(root,path,folder,resume=resume)
            if len(self.runs)==2:
                packet=self.packet(path);packet['failed_todo']=packet['remaining'][1]
                save(folder/'replan-request.json',packet)
            return code
        self.codes=[20,20,0]
        with patch.object(self,'runner',side_effect=fail_next):self.assertEqual(self.run_flow()['code'],0)
        self.assertEqual(len(self.reviews),2)

    def test_context_contains_failure_plan_architecture_and_interfaces_not_bodies(self):
        prompt,info=build(self.root,self.packet(self.path),'qwen')
        for text in ('not ok 1 - empty input','normalize(text)','original_plan_overview'):self.assertIn(text,prompt)
        self.assertNotIn('PRIVATE_BODY_SENTINEL',prompt);self.assertEqual(info['mode'],'complete_architecture_and_shadow')
        (self.root/'one.py').write_text('x=1')
        packet=self.packet(self.path);packet['current_snapshot']='stale'
        with self.assertRaisesRegex(ValueError,'stale'):build(self.root,packet,'qwen')

    def test_stall_evidence_is_reviewed_once_then_escalated_on_repeat(self):
        original=self.packet
        def stalled(path):
            packet=original(path)
            packet.update(reason='no_progress',execution_progress={'rounds_without_progress':5})
            return packet
        self.codes=[20,20]
        with patch.object(self,'packet',side_effect=stalled):
            result=self.run_flow()
        self.assertEqual(result['code'],20);self.assertEqual(len(self.reviews),1)
        self.assertEqual(len(self.runs),2)
        self.assertEqual(read(self.folder/'replan-request.json')['reason'],'no_progress')
        self.assertEqual(self.run_flow(resume=True)['code'],20)
        self.assertEqual(len(self.runs),2)

    def test_reviewer_gets_bounded_investigation_and_measured_context_pressure(self):
        packet=self.packet(self.path);session=self.base/'session';session.mkdir()
        packet['session']=str(session)
        save(session/'execution-progress.json',{'brief':{'status':'stop','rounds_without_progress':5,
            'recent_errors':[{'error':'exact text mismatch'}]}})
        save(session/'launch.json',{'project':str(self.root),'role':'code',
            'effective_settings':{'reasoning_budget':2048},'command':['PRIVATE_LAUNCH_BODY']})
        (session/'pi-config').mkdir()
        save(session/'pi-config/settings.json',{'compaction':{'reserveTokens':50176}})
        save(session/'pi-config/models.json',{'providers':{'local-qwen-workflow':{'models':[{'contextWindow':65536}]}}})
        prompt,_=build(self.root,packet,'qwen')
        for text in ('rounds_without_progress','exact text mismatch','compaction_trigger','task_input_cap'):
            self.assertIn(text,prompt)
        self.assertNotIn('PRIVATE_BODY_SENTINEL',prompt)
        self.assertIn('effective_executor_controls',prompt);self.assertIn('reasoning_budget',prompt)
        self.assertNotIn('PRIVATE_LAUNCH_BODY',prompt)
        self.assertIn('"compaction_trigger":15360',prompt)
        self.assertIn('"trigger_source":"recorded_session_settings"',prompt)

    def test_large_shadow_is_selected_for_qwen_and_fits_cloud_review(self):
        (self.root/'architecture.md').write_text('# Normalization\none.py\n'+'boundary '*35000)
        packet=self.packet(self.path);qwen,q=build(self.root,packet,'qwen');cloud,c=build(self.root,packet,'chatgpt')
        self.assertEqual(q['mode'],'selected_architecture_and_shadow')
        self.assertEqual(c['mode'],'complete_architecture_and_shadow')
        self.assertLess(q['packet_estimated_tokens'],28000);self.assertLess(c['packet_estimated_tokens'],120000)


if __name__=='__main__':unittest.main()
