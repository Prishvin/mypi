"""Accepted historical retries never block a later recovery's pending queue."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import plans
from project_map import scan
from runner_process import read
from retry_handoff import prepare, target
from plan_runner import execute
from test_plan_runner import todo


class RetryHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'project';self.root.mkdir()
        (self.root/'architecture.md').write_text('# Architecture\nPure transformation.\n')
        self.path=self.base/'repair.json';self.folder=self.base/'run';self.folder.mkdir()
        self.fixture=self.base/'accept.py';self.fixture.write_text('assert True\n')
        task=todo('T2');task['tests']=[['python3',str(self.fixture)]]
        plans.save(self.root,['.'],{'plan_version':3,'goal':'Synthetic recovery',
            'architecture':'Pure transformation.','tasks':[task]},self.path)
        self.plan=read(self.path)
        self.plan['replan_lineage']={'parent_plan':'/prior/plan.json','snapshot':scan(self.root,['.'])['snapshot'],
            'completed':[{'id':'T1','status':'done','files':[]}]}
        self.plan['operational_retry']={'todo':'T1','session':'/prior/session'}
        self.path.write_text(json.dumps(self.plan))

    def test_completed_retry_is_recorded_without_creating_an_old_resume_prompt(self):
        before=copy.deepcopy(self.plan);state={}
        with patch('retry_handoff.write_brief') as brief:
            prepare(self.plan,self.folder,state,'current snapshot')
        brief.assert_not_called();self.assertEqual(self.plan,before)
        self.assertEqual(state['historical_retry_ignored']['todo'],'T1')
        self.assertNotIn('resume_prompt',state)

    def test_pending_retry_keeps_its_original_scoped_brief(self):
        self.plan['operational_retry']['todo']='T2';state={}
        with patch('retry_handoff.write_brief') as brief:
            prepare(self.plan,self.folder,state,self.plan['replan_lineage']['snapshot'])
        self.assertEqual(brief.call_args.args[1]['id'],'T2');self.assertEqual(state['resume_todo'],'T2')
        with self.assertRaisesRegex(ValueError,'source changed'):
            prepare(self.plan,self.folder,{},'wrong')

    def test_unknown_target_rejected_before_worker_launch_even_on_resume(self):
        self.plan['operational_retry']['todo']='unknown';self.path.write_text(json.dumps(self.plan))
        with patch('retry_handoff.write_brief') as brief:
            for resume in (False,True):
                with self.assertRaisesRegex(ValueError,'neither pending nor accepted'):
                    execute(self.root,self.path,self.folder,resume=resume)
        brief.assert_not_called()

    def test_real_runner_starts_next_pending_todo_without_replaying_accepted_ancestor(self):
        calls=[]
        def stop(argv,*args):calls.append(argv);raise KeyboardInterrupt()
        with patch('run_metrics.collect',return_value={}):
            self.assertEqual(execute(self.root,self.path,self.folder,stop),130)
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][calls[0].index('--todo')+1],'T2')
        self.assertNotIn('--prompt-file',calls[0])
        state=read(self.folder/'state.json')
        self.assertEqual(state['historical_retry_ignored']['todo'],'T1')
        self.assertEqual(read(self.path)['operational_retry'],self.plan['operational_retry'])

    def test_bootstrap_failure_is_visible_as_scheduler_error_not_test_failure(self):
        self.plan['operational_retry']['todo']='T2';self.path.write_text(json.dumps(self.plan))
        with patch('retry_handoff.write_brief',side_effect=RuntimeError('synthetic startup failure')):
            with self.assertRaisesRegex(RuntimeError,'startup failure'):
                execute(self.root,self.path,self.folder)
        state=read(self.folder/'state.json')
        self.assertEqual(state['status'],'interrupted');self.assertEqual(state['current_todo'],'T2')
        self.assertIn('Scheduler error',state['reason']);self.assertEqual(state['attempts'],[])
        self.assertEqual(read(self.folder/'scheduler-error.json')['type'],'RuntimeError')
        self.assertFalse((self.folder/'replan-request.json').exists())
        from run_monitor import RunMonitor
        monitor=RunMonitor(self.base)
        with patch.object(monitor,'selected',return_value=self.folder),patch.object(monitor,'telemetry',return_value={}):
            status=monitor.snapshot()
        self.assertEqual(status['status'],'interrupted');self.assertIn('startup failure',status['reason'])
        self.assertEqual(status['current_todo'],'T2');self.assertEqual(status['accepted'],1)


if __name__=='__main__':unittest.main()
