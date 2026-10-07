"""Native retries preserve behavior/evidence and cannot turn failures into accepted work."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import plans
import tasks
from plan_runner import execute,REPLAN_EXIT
from retry_plan import create
from runner_process import read
from test_plan_runner import todo


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'project';self.root.mkdir()
        self.plan=self.base/'plan.json';self.run=self.base/'run-1';self.out=self.base/'retry.json'
        self.fixture=self.base/'accept.py';self.fixture.write_text('assert True\n')
        task=todo();task['tests']=[['python3',str(self.fixture)]]
        plans.save(self.root,['.'],{'plan_version':3,'goal':'Identity','architecture':'Pure function.', 'tasks':[task]},self.plan)
        def fail(command,folder,timeout):
            folder.mkdir(parents=True);session=self.base/'session';session.mkdir()
            selected=read(self.plan)['tasks'][0]
            tasks.begin(self.root,['.'],selected,session/'task-state.json')
            (self.root/'slug.py').write_text('def slugify(x):\n    """Normalize case."""\n    return x.lower()\n')
            tasks.run_tests(session/'task-state.json')
            return {'exit_code':124,'session':str(session),'wall_seconds':60}
        with patch('run_metrics.collect',return_value={}):self.assertEqual(execute(self.root,self.plan,self.run,fail),REPLAN_EXIT)
    def test_native_retry_preserves_all_behavior_and_original_failed_baseline(self):
        before=self.plan.read_bytes();result=create(self.root,self.run,self.out,2700)
        old=read(self.plan)['tasks'][0];new=read(self.out)['tasks'][0]
        for key in ('id','goal','files','tests','acceptance','coverage','context','steps'):
            self.assertEqual(new[key],old[key])
        self.assertEqual(new['execution']['timeout_seconds'],2700);self.assertEqual(new['status'],'todo')
        self.assertEqual(new['baseline'],str(self.base/'session/task-state.json'))
        self.assertEqual(self.plan.read_bytes(),before);self.assertIn('preserved',result['note'])
    def test_source_drift_and_changed_immutable_fixture_block_retry(self):
        p=self.root/'slug.py';p.write_text(p.read_text()+'# unexpected edit\n')
        with self.assertRaisesRegex(ValueError,'Source changed'):create(self.root,self.run,self.out)
        self.assertFalse(self.out.exists())
    def test_acceptance_fixture_and_contract_tampering_block_retry(self):
        self.fixture.write_text('assert False\n')
        with self.assertRaisesRegex(ValueError,'fixture'):create(self.root,self.run,self.out)
        self.assertFalse(self.out.exists())
    def test_failed_scope_is_not_grandfathered_and_invalid_timeout_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'timeout'):create(self.root,self.run,self.out,9999)
        self.assertFalse(self.out.exists())
    def test_refuses_overwrite_or_nonfailed_run(self):
        self.out.write_text('preserve')
        with self.assertRaises(ValueError):create(self.root,self.run,self.out)
        self.assertEqual(self.out.read_text(),'preserve')
        self.out.unlink();state=read(self.run/'state.json');state['status']='running'
        (self.run/'state.json').write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError,'stopped'):create(self.root,self.run,self.out)
