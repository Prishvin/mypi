"""Coverage references, gaps and native preservation are enforceable plan contracts."""
import copy
import unittest
from coverage_plan import annotate,validate,require_gaps
from test_plan_runner import todo


def draft():
    tasks=[todo('T1','one.py'),todo('T2','two.py')]
    for task in tasks:task['tests']=[['python3','-c','assert True']]
    tasks[1]['depends_on']=['T1']
    return {'plan_version':3,'goal':'Normalize','architecture':'Pure contracts','tasks':tasks}


def coverage(plan):
    checks=[{'task':t['id'],'criterion':c['id'],'level':'unit','test':0,'oracle':c['then']}
            for t in plan['tasks'] for c in t['acceptance']]
    return {'strategy':{'unit':'Pure inputs and outputs','integration':'Module contract checks',
                       'e2e':'Not applicable: library only'},'checks':checks,'gaps':[],
            'requirements':[{'requirement':'Normalize inputs','cases':[
                {'task':c['task'],'criterion':c['criterion']} for c in checks]}]}


def gap():
    return {'task':'T1','case':{'id':'T1-empty','given':'Empty string','when':'Normalized','then':'Empty string'},
            'level':'unit','test':['node','--test','test/empty.test.mjs'],'reason':'Missing boundary behavior'}


class CoverageTests(unittest.TestCase):
    def test_annotation_preserves_contracts_and_is_independent(self):
        original=draft();result=annotate(original,{'coverage_plan':coverage(original)})
        self.assertEqual(result['tasks'],original['tasks']);self.assertEqual(result['architecture'],original['architecture'])
        result['tasks'][0]['goal']='Changed';self.assertNotEqual(result['tasks'],original['tasks'])

    def test_all_cases_require_oracles_and_valid_command_mapping(self):
        plan=draft()
        changes=[lambda c:c['checks'].pop(),lambda c:c['checks'][0].update(oracle=' '),
                 lambda c:c['checks'][0].update(task='UNKNOWN'),lambda c:c['checks'][0].update(level='manual'),
                 lambda c:c['checks'][0].update(test=1),lambda c:c['checks'][0].update(test=True),
                 lambda c:c['checks'][0].update(criterion='absent')]
        for mutate in changes:
            data=coverage(plan);mutate(data)
            with self.subTest(data=data),self.assertRaises(ValueError):validate(plan,data)
        plan['tasks'][0]['tests'].append(['node','--test']);data=coverage(plan);data['checks'][0]['test']=1
        with self.assertRaisesRegex(ValueError,'mapping'):validate(plan,data)

    def test_requirements_must_trace_all_cases_and_gaps(self):
        plan=draft();data=coverage(plan);data['gaps']=[gap()]
        with self.assertRaisesRegex(ValueError,'link'):validate(plan,data)
        data['requirements'][0]['cases'].append({'task':'T1','criterion':'T1-empty'});validate(plan,data)
        data['requirements'][0]['cases'].append({'task':'T2','criterion':'made-up'})
        with self.assertRaisesRegex(ValueError,'unknown'):validate(plan,data)

    def test_gaps_have_unique_known_owners_and_observable_cases(self):
        plan=draft()
        for edit in ({'task':'UNKNOWN'},{'case':plan['tasks'][0]['acceptance'][0]}, {'test':[]},
                     {'reason':''},{'level':'other'},{'case':{'id':'missing-fields'}}):
            data=coverage(plan);data['gaps']=[{**gap(),**edit}]
            with self.subTest(edit=edit),self.assertRaises(ValueError):validate(plan,data)
        data=coverage(plan);data['gaps']=[gap(),gap()]
        with self.assertRaisesRegex(ValueError,'unique'):validate(plan,data)

    def test_each_test_layer_needs_an_explanation_and_no_contract_edits(self):
        plan=draft();data=coverage(plan);data['strategy'].pop('e2e')
        with self.assertRaises(ValueError):validate(plan,data)
        with self.assertRaises(ValueError):annotate(plan,{'coverage_plan':coverage(plan),'task_updates':[]})

    def test_gap_needs_exact_case_command_and_coverage_in_the_same_task(self):
        tasks=draft()['tasks'];missing=gap()
        require_gaps(tasks,[missing],'T2')
        for stage in range(3):
            with self.assertRaisesRegex(ValueError,'incorporate'):require_gaps(tasks,[missing],'T1')
            if stage==0:tasks[0]['acceptance'].append(missing['case'])
            elif stage==1:tasks[0]['tests'].append(missing['test'])
            else:tasks[0]['coverage'].append({'criterion':'T1-empty','test':1})
        require_gaps(tasks,[missing],'T1')


if __name__=='__main__':unittest.main()
