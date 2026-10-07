"""Real contract assembly and checkpoints; only the model transport is simulated."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import plans
from plan_draft import bind,restore
from plan_runner import execute,validate
from project_map import scan
from runner_process import read,save
from staged_planning import create
from test_coverage_plan import draft,coverage


class StagedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'project';self.root.mkdir()
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        self.output=self.base/'final.json';self.folder=self.base/'final.stages'
        self.calls=[];self.failure=None;self.split=False
        self.addCleanup(patch.stopall)
        patch('plan_refinement.review',side_effect=self.review).start()
        patch('plan_refinement.review_coverage',side_effect=self.coverage).start()

    def draft(self,project,request,output,planner,timeout,**options):
        self.calls.append('DRAFT');self.assertTrue(options['require_refinement'])
        data=draft();data['planning_review']={'required':True,'status':'draft'}
        plans.save(project,['.'],data,output)
        return {'passed':True,'plan':str(output),'pipeline':{'refined_prompt':request+' clarified'}}

    def save_patch(self,project,current,output,change,*,target=None,coverage_mode=False):
        bound=output.with_suffix('.binding.json')
        bind(project,current,bound,scan(project,['.'])['snapshot'],target,coverage_mode)
        plans.save(project,['.'],restore(project,['.'],bound,change),output)
        return {'passed':True,'plan':str(output)}

    def coverage(self,project,request,current,output,planner,timeout):
        self.calls.append('COVERAGE');self.assertIn('clarified',request)
        if self.failure=='COVERAGE':return {'passed':False}
        return self.save_patch(project,current,output,{'coverage_plan':coverage(read(current))},coverage_mode=True)

    def review(self,project,request,original,current,target,output,planner,timeout):
        self.calls.append(target);self.assertIn('clarified',request)
        if self.failure==target:return {'passed':False,'plan':str(output)}
        if self.failure=='interrupt-'+target:raise KeyboardInterrupt()
        change={'id':target}
        if self.split and target=='T1':
            task=read(current)['tasks'][0];first=copy.deepcopy(task);first['id']='T1a'
            last=copy.deepcopy(task);last['depends_on']=['T1a'];change['replace_with']=[first,last]
        return self.save_patch(project,current,output,{'task_updates':[change]},target=target)

    def run_plan(self,**values):
        return create(self.root,'Build',self.output,values.get('planner','qwen'),60,self.draft,{},values.get('refiner'))

    def test_full_sequence_publishes_only_fully_reviewed_valid_plan(self):
        result=self.run_plan();self.assertTrue(result['passed']);self.assertEqual(self.calls,['DRAFT','COVERAGE','T1','T2'])
        final=read(self.output);validate(self.root,final);plans.require_review(final)
        self.assertEqual(final['planning_review']['reviewed_original_tasks'],['T1','T2'])
        self.assertEqual(read(self.folder/'state.json')['status'],'complete')
        self.assertEqual([t['status'] for t in read(self.folder/'queue.json')['tasks']],['done']*4)
        self.assertEqual(list(self.root.iterdir()),[self.root/'.git'])

    def test_split_reviews_each_original_once_and_retains_consumer_dependency(self):
        self.split=True;self.assertTrue(self.run_plan()['passed']);final=read(self.output)
        self.assertEqual([t['id'] for t in final['tasks']],['T1a','T1','T2'])
        self.assertEqual(final['tasks'][-1]['depends_on'],['T1']);self.assertEqual(self.calls.count('T1'),1)

    def test_completed_or_publication_interrupted_run_does_not_repeat_calls(self):
        import staged_planning
        real=staged_planning.checkpoint
        def interrupt(folder,state,**values):
            if values.get('status')=='complete':raise KeyboardInterrupt()
            return real(folder,state,**values)
        with patch('staged_planning.checkpoint',side_effect=interrupt):
            self.assertEqual(self.run_plan()['stage'],'interrupted')
        self.assertTrue(self.output.is_file());before=list(self.calls)
        self.assertTrue(self.run_plan()['passed']);self.assertTrue(self.run_plan()['passed'])
        self.assertEqual(self.calls,before)

    def test_adopted_draft_skips_generation_and_cannot_adopt_executed_work(self):
        from staged_planning import adopt
        source=self.base/'existing.json';plans.save(self.root,['.'],draft(),source)
        self.assertTrue(create(self.root,'Build clarified',self.output,'qwen',60,adopt,{'source':source})['passed'])
        self.assertEqual(self.calls,['COVERAGE','T1','T2'])
        data=read(source);data['tasks'][0]['status']='done';save(source,data)
        with self.assertRaisesRegex(ValueError,'Accepted work'):
            adopt(self.root,'Request',self.base/'bad.json','qwen',60,source=source)

    def test_existing_unrelated_output_is_never_overwritten(self):
        self.output.write_text('{"private":"preserve"}')
        with self.assertRaisesRegex(ValueError,'already exists'):self.run_plan()
        self.assertEqual(read(self.output),{'private':'preserve'});self.assertEqual(self.calls,[])

    def test_failed_coverage_prevents_refinement_and_execution(self):
        self.failure='COVERAGE';result=self.run_plan()
        self.assertEqual(result['stage'],'coverage_failed');self.assertEqual(self.calls,['DRAFT','COVERAGE'])
        self.assertFalse(self.output.exists());path=self.folder/'draft.json'
        with self.assertRaisesRegex(ValueError,'refinement'):plans.select(path,'T1')
        with self.assertRaisesRegex(ValueError,'refinement'):execute(self.root,path,self.base/'run',lambda *a:self.fail('model invoked'))
        self.assertFalse((self.base/'run').exists())

    def test_resume_completed_reviews_without_repeating_them(self):
        self.failure='T2';self.assertFalse(self.run_plan()['passed']);self.assertFalse(self.output.exists())
        self.failure=None;self.assertTrue(self.run_plan()['passed'])
        self.assertEqual(self.calls,['DRAFT','COVERAGE','T1','T2','T2'])
        self.assertEqual(read(self.folder/'state.json')['review_attempts'],3)

    def test_interrupt_resumes_with_new_attempt_destination(self):
        self.failure='interrupt-T1';self.assertEqual(self.run_plan()['stage'],'interrupted')
        self.assertEqual(read(self.folder/'state.json')['review_attempts'],1)
        self.failure=None;self.assertTrue(self.run_plan()['passed'])
        final=read(self.output);self.assertIn('review-01-attempt-2',final['planning_review']['receipts'][0])
        self.assertEqual(self.calls.count('DRAFT'),1);self.assertEqual(self.calls.count('COVERAGE'),1)

    def test_changed_source_blocks_resume_before_another_call(self):
        self.failure='T2';self.run_plan();before=list(self.calls)
        (self.root/'source.py').write_text('x=1\n');self.failure=None
        result=self.run_plan();self.assertFalse(result['passed']);self.assertEqual(self.calls,before)

    def test_changed_current_or_original_checkpoint_blocks_resume(self):
        self.failure='T2';self.run_plan();state=read(self.folder/'state.json');before=list(self.calls)
        for path in [self.folder/'draft.json',Path(state['current_plan'])]:
            original=read(path);changed=copy.deepcopy(original);changed['goal']='Tampered';save(path,changed)
            self.assertFalse(self.run_plan()['passed']);self.assertEqual(self.calls,before);save(path,original)

    def test_other_request_or_provider_cannot_resume_checkpoint(self):
        self.failure='T2';self.run_plan()
        for args in [('Different','qwen','qwen'),('Build','chatgpt','qwen'),('Build','qwen','chatgpt')]:
            with self.subTest(args=args),self.assertRaisesRegex(ValueError,'different request or provider'):
                create(self.root,args[0],self.output,args[1],60,self.draft,{},args[2])

    def test_failed_first_draft_retries_with_new_output_path(self):
        def failed(project,request,path,*args,**kwargs):
            path.write_text('{}');return {'passed':False,'stage':'draft_failed'}
        result=create(self.root,'Build',self.output,'qwen',60,failed,{})
        self.assertFalse(result['passed']);self.assertTrue(self.run_plan()['passed'])
        self.assertTrue((self.folder/'draft-attempt-2.json').exists())

    def test_native_save_marks_sparse_repaired_draft_unexecutable(self):
        initial=self.base/'unaccepted.json';plans.save(self.root,['.'],draft(),initial)
        bound=self.base/'bound.json';bind(self.root,initial,bound,scan(self.root,['.'])['snapshot'])
        incoming=self.base/'incoming.json';save(incoming,{'task_updates':[{'id':'T1'}]})
        output=self.base/'repaired.json'
        env={**os.environ,'QWEN_WORKFLOW_ROLE':'architect','QWEN_WORKFLOW_PLAN_DRAFT':str(bound),
             'QWEN_WORKFLOW_REQUIRE_REFINEMENT':'1','QWEN_WORKFLOW_SESSION':str(self.base)}
        command=[sys.executable,str(Path(__file__).with_name('workflow.py')),'--root',str(self.root),
                 'save-plan','--input',str(incoming),'--output',str(output)]
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        with self.assertRaisesRegex(ValueError,'refinement'):plans.select(output,'T1')


if __name__=='__main__':unittest.main()
