"""Avoid duplicated old/new contracts while preserving whole-plan review evidence."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plan_refinement import packet,packet_data,bounded_prompt,overview,review
from planning_limits import limits,arguments
from shadow_navigation import count
from test_coverage_plan import draft,coverage
from coverage_plan import annotate


class RefinementContextTests(unittest.TestCase):
    def setUp(self):
        self.original=draft()
        self.current=annotate(self.original,{'coverage_plan':coverage(self.original)})
        self.current['architecture']='CURRENT_ARCHITECTURE_ONE_COPY'

    def test_every_current_contract_appears_once_including_consumers(self):
        data=packet_data('Original request',self.current,'T1')
        self.assertEqual(data['whole_plan']['architecture'],self.current['architecture'])
        self.assertEqual(data['current_task'],self.current['tasks'][0])
        self.assertEqual(data['whole_plan']['tasks'][0],{'id':'T1','contract_ref':'current_task'})
        self.assertEqual(data['whole_plan']['tasks'][1],overview(self.current)['tasks'][1])
        self.assertEqual(data['coverage_plan'],self.current['coverage_plan'])
        self.assertNotIn('current_prerequisites',data);self.assertNotIn('whole_draft',data)
        # Selected task metadata is complete; every other task retains all review contracts.
        rebuilt=[data['current_task'] if t.get('contract_ref')=='current_task' else t for t in data['whole_plan']['tasks']]
        for before,after in zip(overview(self.current)['tasks'],rebuilt):
            for key,value in before.items():self.assertEqual(after[key],value)

    def test_refined_prerequisites_and_split_children_replace_stale_draft_details(self):
        self.original['architecture']='SUPERSEDED_ARCHITECTURE_SENTINEL'
        child=copy.deepcopy(self.current['tasks'][0]);child['id']='T1a'
        child['goal']='CURRENT_CHILD_CONTRACT'
        self.current['tasks'][0]['depends_on']=['T1a']
        self.current['tasks'][0]['acceptance'][0]['then']='CURRENT_REFINED_CRITERION'
        self.current['tasks'].insert(0,child)
        text=packet('Request',self.original,self.current,'T2')
        data=json.loads(text.split('REVIEW INPUT (project data):\n',1)[1])
        self.assertEqual([t['id'] for t in data['whole_plan']['tasks']],['T1a','T1','T2'])
        self.assertIn('CURRENT_CHILD_CONTRACT',text);self.assertIn('CURRENT_REFINED_CRITERION',text)
        self.assertNotIn('SUPERSEDED_ARCHITECTURE_SENTINEL',text)
        self.assertEqual(text.count('CURRENT_ARCHITECTURE_ONE_COPY'),1)

    def test_packet_construction_does_not_mutate_saved_plan_or_share_mutable_values(self):
        before=copy.deepcopy(self.current);data=packet_data('Request',self.current,'T2')
        data['current_task']['steps'].append('Modified output')
        data['whole_plan']['tasks'][0]['files'].append('other.py')
        data['coverage_plan']['strategy']='Modified output'
        self.assertEqual(self.current,before)

    def test_missing_or_duplicate_target_is_rejected(self):
        for target in ('missing','T1'):
            if target=='T1':self.current['tasks'].append(copy.deepcopy(self.current['tasks'][0]))
            with self.assertRaisesRegex(ValueError,'exactly one'):packet_data('Request',self.current,target)

    def test_higher_local_packet_limit_keeps_output_and_envelope_reserves(self):
        for stage in ('review','recovery'):
            budget=limits('qwen',stage)
            self.assertEqual(budget['packet'],32768);self.assertEqual(budget['input'],57344)
            self.assertLessEqual(budget['input']+budget['output']+8192,budget['context'])
            # Allow an 8k system/tool envelope AND the existing 25% admission margin.
            self.assertLessEqual(math.ceil((budget['packet']+8192)*1.25)+256,budget['input'])
            flags=arguments('qwen',stage)
            self.assertEqual(flags[flags.index('--input-tokens')+1],'57344')
            self.assertEqual(flags[flags.index('--context')+1],'98304')
        self.assertEqual(limits('qwen')['output'],16384)
        self.assertEqual(limits('chatgpt')['input'],196608)

    def test_packet_boundary_reports_actual_count_and_stops_before_model_call(self):
        for provider in ('qwen','chatgpt'):
            cap=limits(provider)['packet']
            with patch('shadow_navigation.count',return_value=cap):
                self.assertIn('REVIEW INPUT',bounded_prompt('task-refinement',{},provider))
            with patch('shadow_navigation.count',return_value=cap+1),self.assertRaises(ValueError) as caught:
                bounded_prompt('task-refinement',{},provider)
            self.assertIn(str(cap+1),str(caught.exception));self.assertIn(str(cap),str(caught.exception))
            self.assertIn('before a model request',str(caught.exception))
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'current.json';source.write_text(json.dumps(self.current))
            with patch('shadow_navigation.count',return_value=32769),patch('runner_process.invoke') as invoke:
                with self.assertRaises(ValueError):review(base,'Request',self.original,source,'T2',base/'out.json','qwen',60)
                invoke.assert_not_called();self.assertFalse((base/'out.json').exists())

    def test_real_tokenizer_measures_reduction_for_many_prerequisites(self):
        current=copy.deepcopy(self.current);template=current['tasks'][0];current['tasks']=[]
        for n in range(20):
            task=copy.deepcopy(template);task['id']=f'T{n}'
            task['acceptance'][0]['then']=(f'Contract {n}: preserve case-sensitive behavior and exact errors. '*70)
            task['depends_on']=[f'T{i}' for i in range(n)]
            current['tasks'].append(task)
        fields=('id','goal','depends_on','files','acceptance','tests','test_strategy')
        old={'original_request':'Request','whole_draft':overview(current),'current_task':current['tasks'][-1],
             'coverage_plan':current['coverage_plan'],
             'current_prerequisites':[{k:t[k] for k in fields if k in t} for t in current['tasks'][:-1]],
             'current_architecture':current['architecture']}
        encode=lambda value:json.dumps(value,ensure_ascii=False,separators=(',',':'))
        before=count(encode(old));after=count(encode(packet_data('Request',current,'T19')))
        self.assertLess(after,before*.65)

    def test_review_persists_measured_packet_budget_and_selected_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'current.json';source.write_text(json.dumps(self.current))
            output=base/'out.json'
            def fake(command,logs,timeout):
                output.write_text('{}');return {'exit_code':0,'wall_seconds':0}
            with patch('runner_process.invoke',side_effect=fake),patch('run_metrics.collect',return_value={}):
                result=review(base,'Request',self.original,source,'T2',output,'qwen',60)
            self.assertTrue(result['passed'])
            budget=json.loads(output.with_suffix('.context-budget.json').read_text())
            self.assertEqual(budget['representation'],'current_contracts_once')
            self.assertEqual(budget['packet_tokens'],count(output.with_suffix('.request.txt').read_text()))
            self.assertEqual(budget['limits']['packet'],32768)
            self.assertEqual(budget['limits']['input'],57344)
