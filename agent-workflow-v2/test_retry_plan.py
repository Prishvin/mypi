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
        future=todo('T2','other.py');future['tests']=[['python3',str(self.fixture)]];future['depends_on']=['T1']
        plans.save(self.root,['.'],{'plan_version':3,'goal':'Identity','architecture':'Pure function.', 'tasks':[task,future]},self.plan)
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
        self.assertEqual(read(self.out)['tasks'][1],read(self.plan)['tasks'][1])
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

    def no_progress(self):
        state=read(self.run/'state.json');state['reason']='no_progress'
        (self.run/'state.json').write_text(json.dumps(state))
        (self.base/'session/progress-stop.json').write_text(json.dumps({'reason':'no_progress',
            'identity':{'project':str(self.root.resolve()),'task':'T1'}}))

    def test_no_progress_requires_measured_binding_and_explicit_increased_input(self):
        self.no_progress()
        for kwargs,match in [({},'increased input'),({'input_tokens':17000},'operator reason'),
                            ({'input_tokens':16384,'reason':'unchanged'},'increase input'),
                            ({'input_tokens':True,'reason':'invalid'},'integer')]:
            with self.subTest(kwargs=kwargs),self.assertRaisesRegex(ValueError,match):
                create(self.root,self.run,self.out,**kwargs)
        (self.base/'session/progress-stop.json').unlink()
        with self.assertRaisesRegex(ValueError,'bound no-progress'):
            create(self.root,self.run,self.out,input_tokens=16385,reason='Measured compaction pressure')
        self.assertFalse(self.out.exists())

    def test_input_override_preserves_behavior_and_other_budget_fields(self):
        # Widen the fixture window consistently before starting a second native run.
        original=read(self.plan);original['tasks'][0]['context']['window_tokens']=65536
        self.plan.write_text(json.dumps(original));frozen=read(self.base/'session/task-state.json')
        frozen['task']['context']['window_tokens']=65536
        (self.base/'session/task-state.json').write_text(json.dumps(frozen))
        from plan_runner import contract_digest
        state=read(self.run/'state.json');state['contract_digest']=contract_digest(original)
        (self.run/'state.json').write_text(json.dumps(state));self.no_progress()
        before=self.plan.read_bytes()
        create(self.root,self.run,self.out,2700,input_tokens=40960,reason='Repeated compaction before a mutation')
        updated=read(self.out);old=original['tasks'][0];new=updated['tasks'][0]
        for key in ('steps','assumptions','files','tests','acceptance','coverage'):
            self.assertEqual(new[key],old[key])
        expected={**old['context'],'max_input_tokens':40960}
        self.assertEqual(new['context'],expected)
        self.assertEqual(updated['operational_retry']['input_tokens_before'],16384)
        self.assertEqual(updated['operational_retry']['input_tokens_after'],40960)
        self.assertEqual(new['baseline'],str(self.base/'session/task-state.json'))
        self.assertEqual(self.plan.read_bytes(),before)
        self.assertEqual(updated['tasks'][1],original['tasks'][1])

    def test_input_override_cannot_exceed_the_frozen_window(self):
        with self.assertRaisesRegex(ValueError,'window|context'):
            create(self.root,self.run,self.out,input_tokens=40960,reason='Too large for this window')
        self.assertFalse(self.out.exists())
