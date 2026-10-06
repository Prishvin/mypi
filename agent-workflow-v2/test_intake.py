"""Clarification bounds, pending-question persistence and consolidated prompt flow."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from intake import validate
from intake_service import refine
from request_pipeline import prepare


def ask(text='Which platform?'):
    return {'mode':'ask','question':{'text':text,'options':['Browser','CLI']},'assumptions':[],'unresolved':[]}


def ready(text='Build an offline browser SGF viewer with pure parsing.'):
    return {'mode':'ready','refined_prompt':text,'assumptions':[],'unresolved':[]}


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)/'intake'; self.project=Path(self.temp.name)/'project'
        self.project.mkdir()

    def run_mock(self, *decisions):
        return patch('intake_service.run',side_effect=[({'passed':True,'log':'test'},d) for d in decisions])

    def test_clear_request_needs_zero_questions_and_one_run(self):
        with self.run_mock(ready()) as run:
            result=refine(self.project,'Specific request',self.folder)
        self.assertEqual(result['status'],'ready'); self.assertEqual(result['clarifications'],[])
        self.assertEqual(run.call_count,1)

    def test_pending_question_resumes_without_asking_model_again(self):
        with self.run_mock(ask()) as run:
            pending=refine(self.project,'Ambiguous request',self.folder)
        self.assertEqual(pending['status'],'awaiting_clarification')
        self.assertEqual(run.call_count,1)
        with self.run_mock(ready()) as resumed:
            final=refine(self.project,'Ambiguous request',self.folder,answers=['Browser'])
        self.assertEqual(resumed.call_count,1)
        self.assertEqual(final['clarifications'][0]['answer'],'Browser')
        self.assertEqual(final['refined_prompt'],ready()['refined_prompt'])
        with patch('intake_service.run') as no_calls:
            refine(self.project,'Ambiguous request',self.folder,answers=['Browser'])
        no_calls.assert_not_called()

    def test_two_rounds_have_exact_answers_and_third_ask_is_rejected(self):
        with self.run_mock(ask(),ask('Which SGF scope?'),ready()) as run:
            result=refine(self.project,'SGF tool',self.folder,answers=['Browser','Linear only'])
        self.assertEqual(len(result['clarifications']),2); self.assertEqual(run.call_count,3)
        packet=__import__('json').loads(run.call_args.args[2])
        self.assertEqual(packet['answered_rounds'],2)
        self.assertEqual(packet['clarifications'][1]['answer'],'Linear only')
        with self.assertRaisesRegex(ValueError,'no third'):
            validate(ask(),2)

    def test_essential_uncertainty_blocks_after_two_without_another_question(self):
        blocked={'mode':'blocked','assumptions':[],'unresolved':['Required file semantics remain unspecified']}
        with self.run_mock(ask(),ask('Which semantics?'),blocked):
            result=refine(self.project,'Tool',self.folder,answers=['Browser','Unknown'])
        self.assertEqual(result['status'],'blocked')
        with self.assertRaises(ValueError):
            validate({**ready(),'unresolved':['Unknown required scope']},2)

    def test_changed_request_or_backend_cannot_reuse_answers(self):
        with self.run_mock(ask()):
            refine(self.project,'Request A',self.folder)
        for request,backend in [('Request B','chatgpt'),('Request A','qwen')]:
            with self.assertRaisesRegex(ValueError,'changed'):
                refine(self.project,request,self.folder,backend=backend)

    def test_research_gets_only_consolidated_prompt_and_pending_blocks_it(self):
        output=Path(self.temp.name)/'plan.json'
        with patch('request_pipeline.refine',return_value={'status':'awaiting_clarification'}),patch('request_pipeline.research') as research:
            self.assertFalse(prepare(self.project,'Original',output,'chatgpt',300)['passed'])
            research.assert_not_called()
        with patch('request_pipeline.refine',return_value={'status':'ready','refined_prompt':'One combined prompt'}),patch('request_pipeline.research',return_value={'passed':True}) as research:
            result=prepare(self.project,'Original',output,'chatgpt',300)
        self.assertEqual(research.call_args.args[1],'One combined prompt')
        self.assertEqual(result['refined_prompt'],'One combined prompt')

    def test_research_failure_reports_exit_timeout_and_exact_process_log(self):
        output=Path(self.temp.name)/'plan.json'
        for exit_code, expected in [(1,'code 1'),(124,'timed out'),(0,'required verified draft')]:
            failure={'passed':False,'exit_code':exit_code,'log':'/evidence/research/pi.log'}
            with patch('request_pipeline.research',return_value=failure):
                result=prepare(self.project,'Original',output,'qwen',300,clarifier='off')
            self.assertFalse(result['passed'])
            self.assertEqual(result['stage'],'research_failed')
            self.assertIn(expected,result['error'])
            self.assertIn(failure['log'],result['error'])
            self.assertEqual(__import__('json').loads(output.with_suffix('.pipeline-result.json').read_text())['error'],result['error'])


if __name__=='__main__': unittest.main()
