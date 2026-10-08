"""Exercise reporter variants, crowded output and historical recovery refresh."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from failure_diagnostics import summarize
from failure_refresh import refresh


class DiagnosticTests(unittest.TestCase):
    def test_decorated_node_causes_survive_many_repeated_failure_names(self):
        names = '\n'.join(f'✖ case {i} (0.52ms)' for i in range(25))
        log = names+'\nℹ tests 27\nℹ pass 2\nℹ fail 25\n'+names
        log += '\n  TypeError [Error]: fixture is not a function\n'*25
        log += '    at createThing (file:///project/private.mjs:42:47)\nPRIVATE_IMPLEMENTATION();\n'
        result = summarize(log)
        self.assertEqual(result['observations'][0], 'TypeError [Error]: fixture is not a function')
        self.assertEqual(result['test_summary'], {'tests': 27, 'pass': 2, 'fail': 25})
        self.assertEqual(len(result['observations']), 16)
        self.assertEqual(result['diagnostic_omissions']['other_observations'], 10)
        self.assertNotIn('PRIVATE_IMPLEMENTATION', str(result))
        self.assertNotIn('private.mjs', str(result))

    def test_plain_decorated_and_python_exceptions_are_retained(self):
        for text in ['TypeError: invalid value', 'AssertionError [ERR_ASSERTION]: mismatch',
                     'ValueError: bad input', 'pkg.CustomException: failed', 'Error: no fixture',
                     '\x1b[31mReferenceError [Error]: missing\x1b[0m']:
            with self.subTest(text=text):
                self.assertEqual(len(summarize(text)['observations']), 1)
                self.assertNotIn('\x1b', str(summarize(text)))

    def test_unittest_and_tap_counts_and_assertion_fields(self):
        result = summarize('Ran 9 tests in 0.1s\nFAILED (failures=1)\nAssertionError: 1 != 2\n')
        self.assertEqual(result['test_summary']['tests'], 9)
        result = summarize('# tests 4\n# pass 3\n# fail 1\nerror: expected value\nexpected: 2\nactual: 1\n')
        self.assertEqual(result['test_summary'], {'tests': 4, 'pass': 3, 'fail': 1})
        self.assertIn('actual: 1', result['observations'])
        self.assertEqual(summarize('unrecognized reporter')['test_summary'], {})

    def test_many_distinct_errors_remain_bounded_and_mark_omissions(self):
        result = summarize('\n'.join('Error: '+str(i)+'x'*1000 for i in range(30)))
        self.assertEqual(len(result['observations']), 8)
        self.assertEqual(result['diagnostic_omissions']['causes'], 22)
        self.assertTrue(all(len(line)<=300 for line in result['observations']))


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.project = self.base/'project'; self.project.mkdir()
        self.session = self.base/'session'; self.session.mkdir()
        self.log = self.session/'test.log'; self.log.write_text('TypeError [Error]: fixture is not callable\nℹ tests 3\nℹ pass 1\nℹ fail 2\n')
        self.task = {'id':'T1', 'files':['unit.mjs'], 'tests':[['node','--test']], 'acceptance':[{'id':'A','then':'works'}]}
        self.state = {'before':{'root':str(self.project)}, 'task':self.task,
                      'evidence':{'results':[{'argv':['node','--test'],'exit_code':1,'log':str(self.log)}]}}
        self.state_path = self.session/'task-state.json'; self.save()
        self.packet = {'project':str(self.project),'session':str(self.session),'failed_todo':self.task,
                       'failed_tests':[{'observations':['case name only']}], 'reason':'timeout'}

    def save(self):
        self.state_path.write_text(json.dumps(self.state))

    def test_historical_packet_and_state_stay_unchanged_while_errors_are_repaired(self):
        old = copy.deepcopy(self.packet); state_bytes = self.state_path.read_bytes()
        result = refresh(self.packet)
        self.assertEqual(self.packet, old); self.assertEqual(self.state_path.read_bytes(), state_bytes)
        self.assertEqual(result['reason'], 'timeout')
        self.assertIn('fixture is not callable', result['failed_tests'][0]['observations'][0])
        self.assertEqual(result['failed_tests'][0]['test_summary']['fail'], 2)
        self.assertEqual(len(result['diagnostics_refresh']['logs'][0]['sha256']), 64)

    def test_cross_project_or_changed_contract_cannot_supply_diagnostics(self):
        for key, value in [('project',str(self.base/'other')), ('failed_todo',{**self.task,'id':'T2'})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                refresh({**self.packet,key:value})

    def test_log_escape_and_missing_log_are_rejected(self):
        for path in [self.base/'private.log',self.session/'missing.log']:
            with self.subTest(path=path):
                self.state['evidence']['results'][0]['log'] = str(path); self.save()
                with self.assertRaises(ValueError): refresh(self.packet)

    def test_no_session_packet_is_not_fabricated(self):
        value = {'reason':'external failure'}
        self.assertEqual(refresh(value), value)
        self.assertIsNot(refresh(value), value)

    def test_unrelated_recorded_command_is_rejected(self):
        self.state['evidence']['results'][0]['argv'] = ['unrelated']; self.save()
        with self.assertRaisesRegex(ValueError, 'command'): refresh(self.packet)

    def test_planning_service_pins_refreshed_packet_for_prompt_and_plan_tool(self):
        from planning_service import create_draft
        source = self.base/'original-evidence.json'
        source.write_text(json.dumps({**self.packet,'current_snapshot':'snapshot'}))
        original = source.read_bytes(); output = self.base/'corrected.json'
        with patch('planning_service.scan',return_value={'snapshot':'snapshot'}), \
             patch('failure_context.build',return_value=('Corrected brief',{})) as build, \
             patch('planning_service.invoke',return_value={'exit_code':1,'session':None}) as invoke, \
             patch('run_metrics.collect',return_value={}):
            create_draft(self.project,'Review',output,'qwen',600,source)
        self.assertEqual(source.read_bytes(),original)
        prompt_packet = build.call_args.args[1]
        self.assertIn('fixture is not callable',prompt_packet['failed_tests'][0]['observations'][0])
        argv = invoke.call_args.args[0]
        pinned = Path(argv[argv.index('--replan-evidence')+1])
        self.assertEqual(pinned,output.with_suffix('.evidence.json').resolve())
        self.assertEqual(json.loads(pinned.read_text()),prompt_packet)


if __name__ == '__main__':
    unittest.main()
