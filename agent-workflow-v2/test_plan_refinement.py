"""A task review can improve/split its target without changing unrelated contracts."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from coverage_plan import annotate
from plan_draft import apply,bind,restore
from plan_refinement import guard,packet,review,review_coverage
from project_map import scan
from test_coverage_plan import draft,coverage,gap


class RefinementTests(unittest.TestCase):
    def test_duplicate_target_entries_get_actionable_error_in_native_and_serialized_forms(self):
        updates=[{'id':'T1','steps':['Implement','Test']},{'id':'T1','add_coverage':[]}]
        for value in (updates,json.dumps(updates)):
            with self.assertRaises(ValueError) as caught:guard(draft(),{'task_updates':value},'T1')
            message=str(caught.exception)
            self.assertIn("Received 2 entries with IDs ['T1', 'T1']",message)
            self.assertIn('Combine all changes into ONE',message)
        for value in (None,{},42,[None],['T1']):
            with self.assertRaisesRegex(ValueError,'array containing objects'):
                guard(draft(),{'task_updates':value},'T1')

    def test_target_scope_and_split_dependency_gate(self):
        plan=draft()
        for change in ({'task_updates':[]},{'task_updates':[{'id':'T1'},{'id':'T2'}]},
                       {'task_updates':[{'id':'T2'}]}):
            with self.assertRaises(ValueError):guard(plan,change,'T1')
        children=[copy.deepcopy(plan['tasks'][1]) for _ in range(2)]
        children[0]['id']='T2a';children[1]['depends_on']=['T1','T2a']
        change={'task_updates':[{'id':'T2','replace_with':children}]}
        result=apply(plan,guard(plan,change,'T2'));self.assertEqual([t['id'] for t in result['tasks']],['T1','T2a','T2'])
        for key,value in [('depends_on',['T1']),('id','T2b')]:
            bad=copy.deepcopy(change);bad['task_updates'][0]['replace_with'][-1][key]=value
            with self.assertRaises(ValueError):guard(plan,bad,'T2')

    def test_split_cannot_drop_cases_files_or_tests(self):
        plan=draft();children=[copy.deepcopy(plan['tasks'][0]) for _ in range(2)]
        children[0]['id']='T1a';children[1]['depends_on']=['T1a']
        for field in ('acceptance','files','tests'):
            bad=copy.deepcopy(children)
            for item in bad:item[field]=[]
            change={'task_updates':[{'id':'T1','replace_with':bad}]}
            with self.subTest(field=field),self.assertRaises(ValueError):apply(plan,guard(plan,change,'T1'))

    def test_bound_modes_preserve_hashes_and_require_assigned_gaps(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);root=base/'project';root.mkdir();source=base/'draft.json';bound=base/'bound.json'
            plan=draft();data=coverage(plan);data['gaps']=[gap()]
            data['requirements'][0]['cases'].append({'task':'T1','criterion':'T1-empty'})
            source.write_text(json.dumps(plan));snapshot=scan(root,['.'])['snapshot']
            bind(root,source,bound,snapshot,coverage=True)
            enriched=restore(root,['.'],bound,{'coverage_plan':data})
            self.assertEqual(enriched['tasks'],plan['tasks'])
            source.write_text(json.dumps(enriched));bind(root,source,bound,snapshot,'T1')
            with self.assertRaisesRegex(ValueError,'incorporate'):restore(root,['.'],bound,{'task_updates':[{'id':'T1'}]})
            updated=restore(root,['.'],bound,{'task_updates':[{'id':'T1','add_acceptance':[gap()['case']],
                'add_tests':[gap()['test']],'add_coverage':[{'criterion':'T1-empty','test':1}]}]})
            self.assertIn(gap()['case'],updated['tasks'][0]['acceptance'])
            with self.assertRaises(ValueError):bind(root,source,bound,snapshot,'T1',coverage=True)
            (root/'new.py').write_text('x=1')
            with self.assertRaisesRegex(ValueError,'stale'):restore(root,['.'],bound,{'task_updates':[{'id':'T1'}]})

    def test_packet_has_whole_draft_target_and_coverage_but_is_bounded(self):
        plan=draft();current=annotate(plan,{'coverage_plan':coverage(plan)})
        text=packet('Original request',plan,current,'T2')
        for value in ('Original request','whole_draft','current_task','coverage_plan','T1-A','T2-A'):self.assertIn(value,text)
        with patch('shadow_navigation.count',return_value=28001),self.assertRaisesRegex(ValueError,'28000'):
            packet('Request',plan,current,'T1')

    def test_fresh_invocations_select_provider_mode_budgets_and_record_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'draft.json';source.write_text(json.dumps(draft()))
            calls=[]
            def fake(command,logs,timeout):
                calls.append(command);Path(command[command.index('--plan')+1]).write_text('{}')
                return {'exit_code':0,'wall_seconds':1}
            with patch('runner_process.invoke',side_effect=fake),patch('run_metrics.collect',return_value={'tokens':42}):
                a=review_coverage(base,'Request',source,base/'coverage.json','qwen',60)
                b=review(base,'Request',draft(),source,'T1',base/'review.json','chatgpt',60)
            self.assertTrue(a['passed'] and b['passed']);self.assertEqual(a['metrics'],{'tokens':42})
            self.assertIn('--plan-coverage',calls[0]);self.assertIn('--reasoning-budget',calls[0])
            self.assertIn('--refine-task',calls[1]);self.assertIn('chatgpt-quality',calls[1])
            self.assertNotIn('--reasoning-budget',calls[1]);self.assertIn('272000',calls[1])
            self.assertNotEqual(calls[0][calls[0].index('--prompt-file')+1],calls[1][calls[1].index('--prompt-file')+1])


if __name__=='__main__':unittest.main()
