"""Handoff size follows measured context, not arbitrary prose character counts."""
import copy
import json
from pathlib import Path
import unittest
from tokenizers import Tokenizer
from compaction_budget import fit


def candidate(task, sources=()):
    data={'task':task,'current_gate':{'passed':False},
          'retrieved_sources':{'entries':list(sources),'omitted':0}}
    return {'summary':'FROZEN ATOMIC TASK HANDOFF\n'+json.dumps(data),
            'stats':{'retained':len(sources),'omitted':0,'invalidated':0}}


class CompactionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.payload={'model':'fixture','messages':[{'role':'system','content':'Keep required instructions'},
            {'role':'user','content':'OLD_HISTORY'*5000}],
            'tools':[{'name':'required_tool','schema':{'type':'object'}}]}

    def test_long_valid_contract_uses_real_tokenizer_and_keeps_all_fields(self):
        task={'goal':'Complete task','steps':['instruction'+str(i) for i in range(1200)],
              'acceptance':[{'id':'A','then':'unchanged'}],'tests':[['node','--test']]}
        item=candidate(task);before=copy.deepcopy(item)
        tokenizer=Tokenizer.from_file(str(Path(__file__).with_name('qwen-tokenizer.json')))
        result=fit(item,self.payload,40960,lambda text:len(tokenizer.encode(text).ids))
        self.assertGreater(len(result['summary']),12000)
        self.assertEqual(json.loads(result['summary'].split('\n',1)[1])['task'],task)
        self.assertLessEqual(result['budget']['admission_tokens'],result['budget']['handoff_budget_tokens'])
        self.assertEqual(result['budget']['input_limit'],40960)
        self.assertEqual(item,before)

    def test_projection_keeps_actual_system_and_tools_and_drops_old_history(self):
        observed=[];original=copy.deepcopy(self.payload)
        fit(candidate({'goal':'current task'}),self.payload,20000,
            lambda text:observed.append(json.loads(text)) or len(text))
        self.assertEqual(self.payload,original)
        self.assertEqual(observed[0]['messages'][0],original['messages'][0])
        self.assertEqual(observed[0]['tools'],original['tools'])
        self.assertNotIn('OLD_HISTORY',json.dumps(observed[0]))

    def test_optional_sources_are_omitted_whole_without_contract_loss(self):
        task={'goal':'g'*5000,'acceptance':[{'then':'preserve'}]}
        item=candidate(task,[{'source':'x'*4000},{'source':'y'*4000},{'source':'z'*4000}])
        before=copy.deepcopy(item);result=fit(item,self.payload,20000,len)
        data=json.loads(result['summary'].split('\n',1)[1])
        self.assertEqual(data['task'],task);self.assertLess(result['stats']['retained'],3)
        self.assertGreater(result['stats']['omitted'],0)
        self.assertTrue(all(len(row['source'])==4000 for row in data['retrieved_sources']['entries']))
        self.assertEqual(item,before)

    def test_oversized_contract_and_missing_envelope_fail_without_repairing_values(self):
        item=candidate({'goal':'x'*20000});before=copy.deepcopy(item)
        with self.assertRaisesRegex(ValueError,'no contract fields were removed'):fit(item,self.payload,8192,len)
        self.assertEqual(item,before)
        for payload in [{}, {'messages':[],'tools':[]}]:
            with self.assertRaises(ValueError):fit(candidate({'goal':'task'}),payload,8192,len)
        with self.assertRaises(ValueError):fit(candidate({'goal':'task'}),self.payload,True,len)

    def test_redundant_diagnostics_can_shrink_before_rejecting_contract(self):
        item=candidate({'goal':'required task'})
        data=json.loads(item['summary'].split('\n',1)[1]);data['investigation']={'recent_tools':[{'text':'x'*12000}]}
        data['failures']=[{'log':'saved.log','exit_code':1,'failed_names':['x'*6000]}]
        item['summary']='FROZEN ATOMIC TASK HANDOFF\n'+json.dumps(data)
        result=fit(item,self.payload,8192,len);body=json.loads(result['summary'].split('\n',1)[1])
        self.assertEqual(body['task'],data['task'])
        self.assertEqual(body['investigation']['omitted_recent_tools'],1)
        self.assertEqual(body['failures'][0]['omitted_failed_names'],1)
        self.assertEqual(body['failures'][0]['log'],'saved.log')


if __name__=='__main__':unittest.main()
