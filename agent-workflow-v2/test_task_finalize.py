"""Exercise the actual skill with live CPU tests, immutable scope and current evidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tasks
from task_finalize import finalize, diagnostic
from skill_runner import prepare,run
from verification_counts import count


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'project';self.root.mkdir()
        self.session=Path(self.tmp.name)/'session';self.session.mkdir();self.state=self.session/'task-state.json'
        (self.root/'architecture.md').write_text('# Architecture\nPreserve this decision.\n')
        task={'id':'T1','goal':'Create identity','files':['logic.py','test_logic.py','architecture.md'],
              'acceptance':[{'id':'A','given':'2','when':'identity','then':'2'}],
              'tests':[[sys.executable,'-m','unittest','test_logic']],
              'context':{'architecture_update_required':True}}
        tasks.begin(self.root,['.'],task,self.state)
        (self.session/'launch.json').write_text(json.dumps({'role':'code','project':str(self.root),'state':str(self.state)}))
    def source(self):
        (self.root/'logic.py').write_text('def identity(x):\n    """Return the input unchanged."""\n    return x\n')
        (self.root/'test_logic.py').write_text('import unittest\nfrom logic import identity\nclass T(unittest.TestCase):\n    def test_value(self):\n        """Assert behavior."""\n        self.assertEqual(identity(2),2)\n')
    def test_missing_deliverables_skip_doomed_test_processes(self):
        with patch('tasks.run_tests') as called:result=finalize(self.session,{'automatic':True})
        called.assert_not_called();self.assertEqual(result['pending_files'],['logic.py','test_logic.py'])
        self.assertFalse(result['passed'])
    def test_passing_tests_request_one_note_then_real_skill_accepts_without_source_changes(self):
        self.source();original=(self.root/'logic.py').read_bytes()
        first=finalize(self.session,{});self.assertTrue(first['tests_passed']);self.assertFalse(first['passed'])
        self.assertIn('workflow_test',first['next_action'])
        prepare(self.session,'task-finalize','code')
        result=run(self.session,'task-finalize',{'architecture_note':'logic.py owns pure identity behavior; test_logic.py verifies its contract.','architecture_title':'T1: identity'},'code')['data']
        self.assertTrue(result['passed']);self.assertEqual(result['tests'][0]['tests_collected'],1)
        self.assertEqual((self.root/'logic.py').read_bytes(),original)
        self.assertIn('# Architecture\nPreserve this decision.',(self.root/'architecture.md').read_text())
        self.assertTrue(tasks.check(self.state)['passed'])
    def test_same_note_is_idempotent_and_fresh_tests_are_reused(self):
        self.source();note={'architecture_note':'logic.py owns identity.'}
        finalize(self.session,note);before=(self.root/'architecture.md').read_bytes()
        with patch('tasks.run_tests',wraps=tasks.run_tests) as tested:result=finalize(self.session,note)
        tested.assert_not_called();self.assertTrue(result['passed'])
        self.assertEqual((self.root/'architecture.md').read_bytes(),before)
    def test_edit_invalidates_evidence_and_failure_cannot_be_accepted(self):
        self.source();finalize(self.session,{'architecture_note':'Identity stays pure.'})
        p=self.root/'logic.py';p.write_text(p.read_text().replace('return x','return x+1'))
        result=finalize(self.session,{});self.assertFalse(result['passed']);self.assertFalse(result['tests_passed'])
        self.assertTrue(result['diagnostics']);self.assertIn('AssertionError',json.dumps(result['diagnostics']))
    def test_failed_tests_do_not_publish_a_completion_note(self):
        self.source();p=self.root/'logic.py';p.write_text(p.read_text().replace('return x','return x+1'))
        result=finalize(self.session,{'architecture_note':'This note must wait for a valid implementation.'})
        self.assertFalse(result['passed']);self.assertNotIn('This note must wait',(self.root/'architecture.md').read_text())
    def test_out_of_scope_edit_blocks_note_and_success(self):
        self.source();(self.root/'outside.py').write_text('x=1\n');before=(self.root/'architecture.md').read_text()
        result=finalize(self.session,{'architecture_note':'Do not hide an unrelated edit.'})
        self.assertFalse(result['passed']);self.assertTrue(any('scope' in v.lower() for v in result['violations']))
        self.assertNotIn('Do not hide',(self.root/'architecture.md').read_text())
    def test_invalid_heading_note_and_non_code_role_are_rejected(self):
        self.source()
        with self.assertRaises(ValueError):finalize(self.session,{'architecture_note':'# Replace document'})
        launch=json.loads((self.session/'launch.json').read_text());launch['role']='inspect'
        (self.session/'launch.json').write_text(json.dumps(launch))
        with self.assertRaises(ValueError):finalize(self.session,{})
    def test_node_counts_handle_spec_tap_zero_and_ansi(self):
        for text,n in [('ℹ tests 15\nℹ pass 15\n',15),('# tests 0\n# pass 0\n',0),('\x1b[32mℹ tests 2\x1b[0m\n',2)]:
            self.assertEqual(count(['node','--test','test.mjs'],text),n)
        self.assertIsNone(count(['custom-runner'],'# tests 42\n'))

    def test_verbose_failures_fit_tool_budget_and_keep_full_local_evidence(self):
        self.source()
        state=json.loads(self.state.read_text());state['task']['tests']*=3
        self.state.write_text(json.dumps(state))
        test=self.root/'test_logic.py'
        test.write_text(test.read_text().replace('self.assertEqual(identity(2),2)',
            'print("\\n".join("Error: "+str(i)+"x"*240 for i in range(20)))\n        self.assertEqual(identity(2),3)'))
        prepare(self.session,'task-finalize','code')
        result=run(self.session,'task-finalize',{},'code')['data']
        self.assertFalse(result['passed']);self.assertTrue(result['feedback_truncated'])
        self.assertLess(len(json.dumps(result).encode()),8192)
        full=json.loads(Path(result['artifact']).read_text())
        self.assertEqual(len(full['diagnostics']),3)
        self.assertGreater(len(json.dumps(full)),8192)

    def test_many_node_names_do_not_hide_individual_assertion_causes(self):
        log=self.session/'node.log'
        names=[f'✖ case {i} ({i}.01ms)' for i in range(6)]
        details=[f'\n{name}\n  AssertionError [ERR_ASSERTION]: distinct cause {i}\n'
                 '    actual: false,\n    expected: true,\n' for i,name in enumerate(names)]
        log.write_text('\n'.join(names)+'\nℹ tests 12\nℹ pass 6\nℹ fail 6\n'+''.join(details))
        result=diagnostic({'log':str(log),'exit_code':1})
        self.assertEqual(result['test_summary'],{'tests':12,'pass':6,'fail':6})
        for i in range(6):self.assertIn(f'AssertionError [ERR_ASSERTION]: distinct cause {i}',result['failures'])
        self.assertEqual(sum(line.startswith('✖') for line in result['failures']),6)
        self.assertEqual(result['diagnostic_omissions']['causes'],0)

    def test_decorated_exception_and_omission_counts_survive_finalization(self):
        log=self.session/'many.log'
        log.write_text('\n'.join(f'\x1b[31mTypeError [E_TEST]: cause {i}\x1b[0m' for i in range(12)))
        result=diagnostic({'log':str(log),'exit_code':1})
        self.assertTrue(all(line.startswith('TypeError [E_TEST]:') for line in result['failures']))
        self.assertEqual(result['diagnostic_omissions']['causes'],4)
