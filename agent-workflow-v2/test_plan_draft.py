"""Prove sparse proposal repair preserves contracts, bindings and final validation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from plan_draft import apply, bind, restore
from project_map import scan


def proposal():
    """Use two independent criteria and an exact combined test argv as preservation fixtures."""
    task={'id':'A','files':['one.mjs','two.mjs','test/one.test.mjs','test/two.test.mjs','architecture.md'],
          'acceptance':[{'id':'a','given':'input','when':'act','then':'one'},
                        {'id':'b','given':'input','when':'act','then':'two'}],
          'tests':[['node','--test','test/one.test.mjs','test/two.test.mjs']],
          'coverage':[{'criterion':'a','test':0},{'criterion':'b','test':0}],
          'context':{'max_input_tokens':24576}}
    return {'plan_version':3,'goal':'Build','architecture':'Stable API. Muzzle t=0.',
            'tasks':[task,{'id':'B','files':['next.mjs'],'acceptance':[{'id':'c'}],
                           'tests':[['node','next.test.mjs']],'context':{},'depends_on':['A']}]}


class DraftTests(unittest.TestCase):
    def test_serialized_array_and_joined_parameters_keep_exact_data(self):
        plain={'task_updates':[{'id':'A','estimated_changed_lines':240}],
               'architecture_replacements':[{'old':'Muzzle t=0.','new':'Muzzle t=0.08.'}]}
        encoded={'task_updates':json.dumps(plain['task_updates']),
                 'architecture_replacements':plain['architecture_replacements']}
        joined={'task_updates':json.dumps(plain)[len('{"task_updates": '):-1]}
        expected=apply(proposal(),plain)
        for candidate in (encoded,joined):
            result=apply(proposal(),candidate)
            self.assertEqual(result['tasks'],expected['tasks'])
            self.assertEqual(result['architecture'],expected['architecture'])
            self.assertTrue(result['draft_repair']['transport_normalization'])
        for bad in ('not JSON','[], "goal": "hidden replacement"','[], "task_updates": []'):
            with self.assertRaises(ValueError):apply(proposal(),{'task_updates':bad})

    def test_split_accepts_only_identical_redundant_aggregate_metadata(self):
        parts=self.split()
        for item in parts:
            item.update(estimated_changed_lines=100,execution={'timeout_seconds':1200},
                        context_overlay={'architecture_update_required':True})
        update={'id':'A','replace_with':parts,'estimated_changed_lines':200,
                'execution':{'timeout_seconds':1200},'context_overlay':{'architecture_update_required':True}}
        result=apply(proposal(),{'task_updates':[update]})
        for item in result['tasks'][:2]:
            self.assertTrue(item['context']['architecture_update_required'])
            self.assertNotIn('context_overlay',item)
        for key,value in [('estimated_changed_lines',201),('execution',{'timeout_seconds':600}),
                          ('context_overlay',{'architecture_update_required':False})]:
            with self.assertRaisesRegex(ValueError,'conflict'):
                apply(proposal(),{'task_updates':[{**update,key:value}]})
    def test_native_store_uses_full_validation_and_role_guard(self):
        import workflow
        from test_plans import example_task
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'project';root.mkdir()
            task=example_task();task.update(steps=['Implement pure function','Test edge cases'],
                assumptions=[],test_strategy='Repeated and empty separators',estimated_changed_lines=30)
            task['context'].update(estimate={'framework':8192,'shadow':0,'source':0,'tests':0,'history':0},
                margin_tokens=2048,max_input_tokens=16384,max_output_tokens=8192)
            task['execution']={'timeout_seconds':600,'test_timeout_seconds':60,'on_failure':'replan'}
            raw={'plan_version':3,'goal':'Build parser','architecture':'Pure parser','tasks':[task]}
            source=base/'draft.json';source.write_text(json.dumps(raw));bound=base/'bound.json'
            bind(root,source,bound,scan(root,['.'])['snapshot'])
            incoming=base/'patch.json';incoming.write_text(json.dumps({'task_updates':[{'id':'T1','estimated_changed_lines':40}]}))
            output=base/'plan.json'
            from types import SimpleNamespace
            args=SimpleNamespace(root=root,prefix=[],briefs=None,command='save-plan',input=incoming,output=output)
            with (patch('workflow.arguments',return_value=args),
                  patch('shadow_navigation.planning_context',return_value=None),
                  patch.dict('os.environ',{'QWEN_WORKFLOW_PLAN_DRAFT':str(bound),'QWEN_WORKFLOW_ROLE':'code'})):
                with self.assertRaisesRegex(ValueError,'architect-only'):workflow.main()
                self.assertFalse(output.exists())
            with (patch('workflow.arguments',return_value=args),
                  patch('shadow_navigation.planning_context',return_value=None),
                  patch.dict('os.environ',{'QWEN_WORKFLOW_PLAN_DRAFT':str(bound),'QWEN_WORKFLOW_ROLE':'architect'})):
                malformed={'task_updates':'[{"id":"T1","steps":["first","second"}]}]'}
                valid=incoming.read_text();incoming.write_text(json.dumps(malformed))
                with self.assertRaisesRegex(ValueError,'task_updates contains malformed JSON at character'):
                    workflow.main()
                self.assertFalse(output.exists())
                self.assertEqual(json.loads(incoming.read_text()),malformed)
                incoming.write_text(valid)
                workflow.main()
            stored=json.loads(output.read_text())
            self.assertEqual(stored['tasks'][0]['estimated_changed_lines'],40)
            self.assertEqual(stored['tasks'][0]['acceptance'],task['acceptance'])
            self.assertEqual(stored['tasks'][0]['status'],'todo')
    def test_metadata_patch_keeps_source_criteria_tests_and_original_immutable(self):
        raw=proposal();before=copy.deepcopy(raw)
        result=apply(raw,{'task_updates':[{'id':'A','estimated_changed_lines':240,
            'context_overlay':{'architecture_update_required':True}}]})
        self.assertEqual(raw,before)
        self.assertEqual(result['tasks'][1],raw['tasks'][1])
        for key in ('acceptance','files','tests','coverage'):
            self.assertEqual(result['tasks'][0][key],raw['tasks'][0][key])
        self.assertEqual(result['tasks'][0]['context']['max_input_tokens'],24576)

    def test_unknown_duplicate_and_ambiguous_patch_fields_are_rejected(self):
        for updates in ([{'id':'missing'}],[{'id':'A'},{'id':'A'}],[{'id':'A','acceptance':[]}],
                        [{'id':'A','replace_with':[]}]):
            with self.subTest(updates=updates),self.assertRaises(ValueError):
                apply(proposal(),{'task_updates':updates})
        with self.assertRaises(ValueError):
            apply(proposal(),{'task_updates':[{'id':'A'}],'goal':'change goal'})

    def test_full_task_fields_in_sparse_patch_name_fields_and_explain_correction(self):
        raw=proposal();before=copy.deepcopy(raw)
        with self.assertRaises(ValueError) as caught:
            apply(raw,{'task_updates':[{'id':'A','context':{'max_input_tokens':8192},'coverage':[]}]})
        message=str(caught.exception)
        self.assertIn('for A: context, coverage',message)
        self.assertIn('use context_overlay for context',message)
        self.assertIn('use add_coverage for coverage',message)
        self.assertEqual(raw,before)
        with self.assertRaisesRegex(ValueError,'for A: unknown_field'):
            apply(raw,{'task_updates':[{'id':'A','unknown_field':True}]})

    def test_additive_integration_fixture_retains_old_command_and_indices(self):
        raw=proposal();command=['node','--test','test/main.test.mjs']
        result=apply(raw,{'task_updates':[{'id':'A','add_files':['test/main.test.mjs'],
            'add_tests':[command,command],'add_coverage':[{'criterion':'a','test':1}]}]})['tasks'][0]
        self.assertEqual(result['tests'],raw['tasks'][0]['tests']+[command])
        self.assertEqual(result['coverage'][0],raw['tasks'][0]['coverage'][0])

    def split(self):
        first=copy.deepcopy(proposal()['tasks'][0]);last=copy.deepcopy(first)
        first.update(id='A1',acceptance=first['acceptance'][:1],tests=[['node','--test','test/one.test.mjs']])
        last.update(acceptance=last['acceptance'][1:],depends_on=['A1'])
        return [first,last]

    def test_split_preserves_union_and_original_final_dependency(self):
        result=apply(proposal(),{'task_updates':[{'id':'A','replace_with':self.split()}]})
        self.assertEqual([t['id'] for t in result['tasks']],['A1','A','B'])
        self.assertEqual(result['tasks'][-1]['depends_on'],['A'])

    def test_split_cannot_drop_criteria_tests_files_or_dependency_target(self):
        for key in ('acceptance','tests','files','id'):
            replacements=self.split()
            for item in replacements:
                item[key]='renamed' if key=='id' else []
            with self.subTest(key=key),self.assertRaises(ValueError):
                apply(proposal(),{'task_updates':[{'id':'A','replace_with':replacements}]})
        replacements=self.split();replacements[0]['id']='B'
        with self.assertRaisesRegex(ValueError,'duplicate'):
            apply(proposal(),{'task_updates':[{'id':'A','replace_with':replacements}]})

    def test_architecture_replacement_is_exact_unique_and_bounded_to_passage(self):
        result=apply(proposal(),{'task_updates':[{'id':'A','estimated_changed_lines':200}],
            'architecture_replacements':[{'old':'Muzzle t=0.','new':'Muzzle t=0.08.'}]})
        self.assertEqual(result['architecture'],'Stable API. Muzzle t=0.08.')
        for old in ('','missing'):
            with self.assertRaises(ValueError):
                apply(proposal(),{'task_updates':[{'id':'A'}],
                    'architecture_replacements':[{'old':old,'new':'new'}]})

    def test_criterion_correction_requires_exact_case_same_id_and_recorded_reason(self):
        raw=proposal();old=raw['tasks'][0]['acceptance'][0];new={**old,'given':'touching wall'}
        correction={'old':old,'new':new,'reason':'Original geometric fixture contradicts the stated radius.'}
        result=apply(raw,{'task_updates':[{'id':'A','criterion_replacements':[correction]}]})
        self.assertEqual(result['tasks'][0]['acceptance'][0],new)
        self.assertEqual(result['draft_repair']['criterion_corrections'][0]['old'],old)
        for broken in ({**correction,'reason':'none'},{**correction,'new':{**new,'id':'different'}},
                       {**correction,'old':{**old,'given':'not exact'}}):
            with self.assertRaises(ValueError):
                apply(raw,{'task_updates':[{'id':'A','criterion_replacements':[broken]}]})

    def test_bound_draft_rejects_changed_source_wrong_root_and_tampered_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'project';root.mkdir();source=Path(directory)/'draft.json'
            source.write_text(json.dumps(proposal()));bound=Path(directory)/'bound.json'
            bind(root,source,bound,scan(root,['.'])['snapshot'])
            patch={'task_updates':[{'id':'A','estimated_changed_lines':240}]}
            self.assertEqual(restore(root,['.'],bound,patch)['tasks'][0]['estimated_changed_lines'],240)
            with self.assertRaisesRegex(ValueError,'binding'):
                other=Path(directory)/'other';other.mkdir();restore(other,['.'],bound,patch)
            data=json.loads(bound.read_text());data['proposal']['goal']='tamper';bound.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'hash'):restore(root,['.'],bound,patch)
            bind(root,source,bound,scan(root,['.'])['snapshot']);(root/'one.mjs').write_text('export const a=1;')
            with self.assertRaisesRegex(ValueError,'stale'):restore(root,['.'],bound,patch)

    def test_execution_evidence_and_in_project_proposals_cannot_use_draft_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'project';root.mkdir();source=Path(directory)/'draft.json'
            bound=Path(directory)/'bound.json'
            for change in ('done','evidence','baseline','lineage'):
                raw=proposal()
                if change=='lineage':raw['replan_lineage']={'completed':[]}
                elif change=='done':raw['tasks'][0]['status']='done'
                else:raw['tasks'][0][change]='saved'
                source.write_text(json.dumps(raw))
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,'Accepted'):
                    bind(root,source,bound,'snapshot')
            source=root/'draft.json';source.write_text(json.dumps(proposal()))
            with self.assertRaisesRegex(ValueError,'outside'):bind(root,source,bound,'snapshot')

    def test_missing_and_oversized_estimates_remain_rejected_by_actual_v3_gate(self):
        from plans import validate_granularity
        task={**proposal()['tasks'][0],'steps':['one','two'],'test_strategy':'real tests','assumptions':[]}
        for value in (None,0,301,'250'):
            candidate=apply({**proposal(),'tasks':[task]}, {'task_updates':[{'id':'A','estimated_changed_lines':value}]})
            with self.subTest(value=value),self.assertRaises(ValueError):validate_granularity(candidate['tasks'][0])
