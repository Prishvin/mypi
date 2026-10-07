"""Historical planning results must remain separate from implementation/test acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from run_monitor import read
from run_planning_results import results,archived


class PlanningResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.a={'id':'A','goal':'Original A','files':['a.py'],'steps':['Write','Test'],
                'tests':[['python3','-m','unittest']],'acceptance':[{'id':'a'}],'source':'PRIVATE SOURCE'}
        self.b={**self.a,'id':'B','goal':'Original B'}
        self.draft={'architecture':'Original architecture','tasks':[self.a,self.b]}
        self.write('draft.json',self.draft)
        self.state={'workflow_phase':'planning','draft_passed':True,'reviewed':[],'reviews':[]}
    def write(self,name,data):
        path=self.root/name;path.write_text(json.dumps(data));return str(path)
    def result(self):return results(self.root,self.state,read)
    def test_draft_and_coverage_expose_exact_saved_outputs_without_source(self):
        coverage={'strategy':{'unit':'Seeded'},'checks':[{'oracle':'Observable'}],
                  'requirements':[{'requirement':'Keep behavior'}],'gaps':[{'reason':'Missing edge'}]}
        path=self.write('coverage.json',{**self.draft,'coverage_plan':coverage})
        self.state.update(coverage_passed=True,coverage_result={'passed':True,'plan':path})
        output=self.result();self.assertEqual(output['DRAFT']['architecture'],'Original architecture')
        self.assertEqual(output['DRAFT']['tasks'][0]['steps'],self.a['steps'])
        self.assertEqual(output['COVERAGE']['coverage'],coverage);self.assertNotIn('PRIVATE',json.dumps(output))
    def test_each_review_uses_its_own_receipt_and_tracks_split_children_and_changed_fields(self):
        first=copy.deepcopy(self.draft);first['tasks'][0]['goal']='Refined A'
        child={**self.a,'id':'A-part','goal':'Child A'};first['tasks'].insert(0,child)
        second=copy.deepcopy(first);second['tasks'][-1]['goal']='Refined B';second['architecture']='Revised architecture'
        self.state.update(reviewed=['A','B'],reviews=[
            {'target':'A','passed':True,'plan':self.write('one.json',first)},
            {'target':'B','passed':True,'plan':self.write('two.json',second)}])
        output=self.result();one=output['REVIEW-01-A'];two=output['REVIEW-02-B']
        self.assertEqual([t['id'] for t in one['tasks']],['A-part','A'])
        self.assertEqual([t['id'] for t in two['tasks']],['B'])
        self.assertEqual(one['tasks'][-1]['goal'],'Refined A')
        self.assertIn({'task':'B','field':'goal','before':'Original B','after':'Refined B'},two['changes'])
        self.assertEqual(two['architecture_change']['before'],'Original architecture')
    def test_failed_incomplete_missing_and_nonplanning_artifacts_are_not_reported_as_saved(self):
        self.state['reviews']=[{'target':'A','passed':False,'plan':self.write('failed.json',self.draft)}]
        self.assertEqual(set(self.result()),{'DRAFT'})
        self.state['reviewed']=['A'];self.state['reviews'][0].update(passed=True,plan=str(self.root/'missing.json'))
        self.assertFalse(self.result()['REVIEW-01-A']['available'])
        self.state['workflow_phase']='execution';self.assertEqual(self.result(),{})
        self.state.update(workflow_phase='planning',draft_passed=False);self.assertEqual(self.result(),{})
    def test_missing_previous_review_never_attributes_another_tasks_split_to_next_review(self):
        later={**self.draft,'tasks':[self.a,{**self.a,'id':'A-part'},self.b]}
        self.state.update(reviewed=['A','B'],reviews=[
            {'target':'A','passed':True,'plan':str(self.root/'missing.json')},
            {'target':'B','passed':True,'plan':self.write('two.json',later)}])
        row=self.result()['REVIEW-02-B'];self.assertFalse(row['comparison_available'])
        self.assertIsNone(row['changes']);self.assertEqual([t['id'] for t in row['tasks']],['B'])
    def test_archived_planning_retains_results_only_for_the_bound_completed_pipeline(self):
        from plan_draft import digest
        fingerprint=digest(self.draft)
        self.write('state.json',{**self.state,'status':'complete','project':str(self.root),'draft_sha256':fingerprint})
        self.write('queue.json',{'tasks':[{'id':'DRAFT','goal':'Plan','status':'done'}]})
        plan={'planning_review':{'coverage_receipt':str(self.root/'coverage.json'),'draft_sha256':fingerprint}}
        rows=archived(plan,self.root,read);self.assertEqual(rows[0]['status'],'Accepted')
        self.assertTrue(rows[0]['planning']);self.assertEqual(rows[0]['planning_result']['tasks'][0]['goal'],'Original A')
        self.assertEqual(archived(plan,self.root/'other',read),[])
        plan['planning_review']['draft_sha256']='different';self.assertEqual(archived(plan,self.root,read),[])


if __name__=='__main__':unittest.main()
