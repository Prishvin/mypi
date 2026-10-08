"""Exercise deterministic scheduling with real independent acceptance fixtures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import plans
import tasks
import shadow
from plan_runner import execute, validate, REPLAN_EXIT
from planning_service import attach_lineage
from runner_process import read


def todo(identifier='T1', filename='slug.py'):
    """Supply a bounded fixture contract with valid V3 context estimates."""
    return {'id': identifier, 'goal': 'Make a lowercase slug', 'files': [filename],
        'steps': ['Inspect the documented contract.', 'Implement pure normalization and run acceptance.'],
        'assumptions': [], 'test_strategy': 'External behavior assertion, no model grading.',
        'estimated_changed_lines': 30,
        'acceptance': [{'id': identifier+'-A', 'given': 'ABC', 'when': 'slugify is called', 'then': 'abc'}],
        'coverage': [{'criterion': identifier+'-A', 'test': 0}], 'tests': [], 'depends_on': [],
        'context': {'interfaces': [filename], 'symbols': [], 'reference_files': [],
            'max_input_tokens': 16384, 'max_output_tokens': 8192, 'window_tokens': 32768,
            'thinking': 'on', 'reasoning_effort': 'medium',
            'estimate': {'framework': 7168, 'shadow': 256, 'source': 512, 'tests': 256, 'history': 1024},
            'margin_tokens': 2304},
        'execution': {'timeout_seconds': 60, 'test_timeout_seconds': 10, 'on_failure': 'replan'}}


class RunnerTests(unittest.TestCase):
    """Prove advancement, stopping, replay protection, drift detection and replan integrity."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base / 'project'; self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.fixture = self.base / 'acceptance.py'
        self.fixture.write_text("import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()))\nfrom slug import slugify\nassert slugify('ABC') == 'abc', 'independent normalization acceptance failed'\n")
        self.source = self.root / 'slug.py'
        self.source.write_text('def slugify(text):\n    """Normalize text to lowercase."""\n    return text\n')
        task = todo(); task['tests'] = [[sys.executable, str(self.fixture)]]
        self.plan = {'plan_version': 3, 'goal': 'Normalize values', 'architecture': 'Pure functions', 'tasks': [task]}
        self.path = self.base / 'plan.json'; self.folder = self.base / 'run'; self.calls = []

    def save(self):
        plans.save(self.root, ['.'], self.plan, self.path)

    def fake(self, command, folder, timeout, *, correct=True, exit_code=0):
        """Simulate only Pi transport; acceptance uses the real independent fixture."""
        identifier = command[command.index('--todo')+1]; self.calls.append(identifier)
        folder.mkdir(parents=True); session = folder / 'session'; session.mkdir()
        task = plans.select(self.path, identifier)
        state = session / 'task-state.json'
        tasks.begin(self.root, ['.'], task, state, session / 'shadow')
        (self.root / task['files'][0]).write_text('def slugify(text):\n    """Normalize text to lowercase."""\n    return text' + ('.lower()' if correct else '') + '\n')
        shadow.refresh(self.root, ['.'], session / 'shadow'); tasks.run_tests(state)
        gate = tasks.check(state); (session / 'final-gate.json').write_text(json.dumps(gate))
        return {'exit_code': exit_code, 'session': str(session), 'wall_seconds': .01}

    def test_success_and_repeat_does_not_call_model_again(self):
        self.save(); self.assertEqual(execute(self.root, self.path, self.folder, self.fake), 0)
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake), 0)
        self.assertEqual(self.calls, ['T1']); self.assertEqual(read(self.folder/'state.json')['status'], 'complete')

    def test_two_todos_run_in_order_and_previous_acceptance_is_rerun(self):
        second = copy.deepcopy(self.plan['tasks'][0]); second.update(id='T2', depends_on=['T1'], files=['other.py'])
        second['tests'] = [[sys.executable, '-c', "from other import slugify; assert slugify('ABC') == 'abc'"]]
        self.plan['tasks'].append(second); self.save()
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake), 0)
        self.assertEqual(self.calls, ['T1', 'T2'])
        self.assertEqual(len(read(self.folder/'state.json')['attempts'][1]['regression']['tests']), 1)

    def test_failed_test_stops_before_dependent_task_even_when_process_claims_success(self):
        second = copy.deepcopy(self.plan['tasks'][0]); second.update(id='T2', depends_on=['T1'])
        self.plan['tasks'].append(second); self.save()
        failed = lambda *a: self.fake(*a, correct=False)
        self.assertEqual(execute(self.root, self.path, self.folder, failed), REPLAN_EXIT)
        self.assertEqual(self.calls, ['T1'])
        packet = read(self.folder/'replan-request.json')
        self.assertEqual(packet['failed_tests'][0]['exit_code'], 1)
        self.assertIn('AssertionError:', packet['failed_tests'][0]['observations'][0])
        self.assertNotIn('return text', packet['selected_prototypes'])
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake), REPLAN_EXIT)
        self.assertEqual(self.calls, ['T1'])

    def test_provider_failure_stops_with_reason(self):
        self.save()
        self.assertEqual(execute(self.root, self.path, self.folder,
            lambda *a: self.fake(*a, exit_code=1)), REPLAN_EXIT)
        self.assertEqual(read(self.folder/'replan-request.json')['reason'], 'execution_failed')

    def test_compaction_failure_is_distinct_from_the_underlying_test_failure(self):
        self.save()
        def failed_compaction(*args):
            result=self.fake(*args,correct=False,exit_code=1)
            (Path(result['session'])/'compaction-error.json').write_text(json.dumps({
                'error':'Complete handoff exceeded measured headroom','modelFallbackAllowed':False}))
            return result
        self.assertEqual(execute(self.root,self.path,self.folder,failed_compaction),REPLAN_EXIT)
        packet=read(self.folder/'replan-request.json')
        self.assertEqual(packet['reason'],'compaction_failed')
        self.assertTrue(packet['failed_tests'])
        self.assertIn('measured headroom',packet['violations'][0])

    def test_node_failure_handoff_carries_assertion_without_trace_source(self):
        """JavaScript failures provide planner observations without implementation lines."""
        from runner_evidence import failed_tests
        session = self.base / 'node-session'; session.mkdir()
        log = session / 'test.log'
        log.write_text('file:///project/render.mjs:25\n  return secretImplementation(state);\n'
                       'AssertionError [ERR_ASSERTION]: enemy behind wall must stay hidden\n'
                       '    at renderFrame (file:///project/render.mjs:25:3)\n')
        (session/'task-state.json').write_text(json.dumps({'evidence': {'results': [
            {'argv': ['node', 'acceptance.mjs'], 'exit_code': 1, 'log': str(log)}]}}))
        rows = failed_tests(str(session))
        self.assertEqual(rows[0]['observations'], [
            'AssertionError [ERR_ASSERTION]: enemy behind wall must stay hidden'])
        self.assertNotIn('secretImplementation', json.dumps(rows))

    def test_timeout_is_not_a_pass_even_if_code_was_correct(self):
        self.save()
        self.assertEqual(execute(self.root, self.path, self.folder,
            lambda *a: self.fake(*a, exit_code=124)), REPLAN_EXIT)
        self.assertEqual(read(self.folder/'replan-request.json')['reason'], 'timeout')

    def test_deadline_remains_stop_reason_when_latest_tests_also_failed(self):
        self.save()
        self.assertEqual(execute(self.root,self.path,self.folder,
            lambda *a:self.fake(*a,correct=False,exit_code=124)),REPLAN_EXIT)
        packet=read(self.folder/'replan-request.json')
        self.assertEqual(packet['reason'],'timeout')
        self.assertTrue(packet['failed_tests'])
        self.assertTrue(any('tests' in v.lower() for v in packet['violations']))

    def test_progress_stop_survives_zero_exit_and_reaches_reviewer_packet(self):
        self.save()
        def stalled(*args):
            result=self.fake(*args,correct=False)
            session=Path(result['session'])
            brief={'status':'stop','rounds_without_progress':5,'recent_errors':[{'error':'text mismatch'}]}
            (session/'progress-stop.json').write_text(json.dumps({'reason':'no_progress',
                'identity':{'project':str(self.root.resolve()),'task':'T1'},'brief':brief}))
            (session/'execution-progress.json').write_text(json.dumps({'brief':brief}))
            return result
        self.assertEqual(execute(self.root,self.path,self.folder,stalled),REPLAN_EXIT)
        packet=read(self.folder/'replan-request.json')
        self.assertEqual(packet['reason'],'no_progress')
        self.assertEqual(packet['execution_progress']['rounds_without_progress'],5)
        self.assertEqual(packet['failed_todo']['acceptance'],self.plan['tasks'][0]['acceptance'])
        current=packet['current_task_gate']
        self.assertTrue(current['available']);self.assertFalse(current['passed'])
        self.assertIn('Declared tests have not all passed',current['violations'])

    def test_progress_stop_from_another_task_cannot_override_acceptance(self):
        self.save()
        def success(*args):
            result=self.fake(*args)
            (Path(result['session'])/'progress-stop.json').write_text(json.dumps({'reason':'no_progress',
                'identity':{'project':str(self.root.resolve()),'task':'DIFFERENT'}}))
            return result
        self.assertEqual(execute(self.root,self.path,self.folder,success),0)

    def test_progress_observer_error_is_reported_instead_of_generic_acceptance_failure(self):
        self.save()
        def broken(*args):
            result=self.fake(*args,correct=False)
            (Path(result['session'])/'progress-error.json').write_text('{"error":"Progress journal truncated"}')
            return result
        self.assertEqual(execute(self.root,self.path,self.folder,broken),REPLAN_EXIT)
        self.assertEqual(read(self.folder/'replan-request.json')['reason'],'progress_monitor_failed')

    def test_missing_evidence_cannot_finish_a_task(self):
        self.save()
        def empty(command, folder, timeout):
            folder.mkdir(); return {'exit_code': 0, 'session': str(folder)}
        self.assertEqual(execute(self.root, self.path, self.folder, empty), REPLAN_EXIT)

    def test_modified_project_cannot_reuse_completed_result(self):
        self.save(); execute(self.root, self.path, self.folder, self.fake)
        self.source.write_text(self.source.read_text().replace('.lower()', ''))
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake), REPLAN_EXIT)
        self.assertEqual(self.calls, ['T1'])

    def test_changed_plan_is_not_silently_resumed(self):
        self.save(); execute(self.root, self.path, self.folder, self.fake)
        plan = read(self.path); plan['tasks'][0]['goal'] = 'Different behavior'; self.path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'changed plan'):
            execute(self.root, self.path, self.folder, self.fake)

    def test_changed_external_fixture_is_rejected_before_inference(self):
        self.save(); self.fixture.write_text('print("pretend pass")\n')
        with self.assertRaisesRegex(ValueError, 'fixture changed'):
            execute(self.root, self.path, self.folder, self.fake)
        self.assertFalse(self.calls)

    def test_bad_budget_policy_and_unsafe_ids_are_rejected(self):
        self.save(); saved = read(self.path)
        for mutate in [lambda t: t['context'].update(margin_tokens=1024),
                       lambda t: t['execution'].update(on_failure='ignore'),
                       lambda t: t.update(id='../escape'),
                       lambda t: t['context'].update(max_input_tokens=8192)]:
            bad = copy.deepcopy(saved); mutate(bad['tasks'][0])
            with self.assertRaises(ValueError): validate(self.root, bad)

    def test_replan_cannot_weaken_acceptance_or_expand_files(self):
        self.save(); original = read(self.path)
        packet = {'remaining': original['tasks'], 'plan': str(self.path), 'reason': 'acceptance_failed',
                  'completed': [], 'current_snapshot': original['snapshot']}
        attach_lineage(copy.deepcopy(original), packet)
        for mutate in [lambda p: p['tasks'][0].update(acceptance=[]),
                       lambda p: p['tasks'][0].update(tests=[]),
                       lambda p: p['tasks'][0].update(files=['surprise.py'])]:
            changed = copy.deepcopy(original); mutate(changed)
            with self.assertRaises(ValueError): attach_lineage(changed, packet)

    def test_identical_failed_atomic_contract_keeps_original_source_baseline(self):
        """An invalid partial edit must not become grandfathered legacy code on replan."""
        self.save();original=read(self.path);session=self.base/'failed';session.mkdir()
        frozen=session/'task-state.json';task=plans.select(self.path,'T1')
        tasks.begin(self.root,['.'],task,frozen,session/'shadow')
        original_text=self.source.read_text();self.source.write_text('def slugify(text):\n    return "bad partial edit"\n')
        packet={'remaining':original['tasks'],'plan':str(self.path),'reason':'acceptance_failed',
            'completed':[],'current_snapshot':original['snapshot'],'session':str(session)}
        candidate=copy.deepcopy(original);attach_lineage(candidate,packet)
        self.assertEqual(candidate['tasks'][0]['baseline'],str(frozen))
        replacement=self.base/'replacement.json';replacement.write_text(json.dumps(candidate))
        fresh=self.base/'fresh-state.json';tasks.begin(self.root,['.'],task,fresh,self.base/'fresh-shadow')
        plans.start_attempt(replacement,'T1',fresh)
        self.assertEqual(read(fresh)['declared_text']['slug.py'],original_text)

    def test_new_task_failure_preserves_previous_done_task(self):
        second = copy.deepcopy(self.plan['tasks'][0]); second.update(id='T2', depends_on=['T1'], files=['other.py'])
        second['tests'] = [[sys.executable, '-c', "from other import slugify; assert slugify('ABC') == 'abc'"]]
        self.plan['tasks'].append(second); self.save()
        def staged(command, folder, timeout):
            return self.fake(command, folder, timeout, exit_code=1 if command[command.index('--todo')+1]=='T2' else 0)
        self.assertEqual(execute(self.root, self.path, self.folder, staged), REPLAN_EXIT)
        packet = read(self.folder/'replan-request.json')
        self.assertEqual([t['id'] for t in packet['completed']], ['T1'])
        self.assertEqual([t['id'] for t in packet['remaining']], ['T2'])

    def test_reordered_acceptance_keeps_failed_original_baseline(self):
        """Formatting/reordering a preserved contract cannot grandfather a bad partial edit."""
        task=self.plan['tasks'][0]
        second=copy.deepcopy(task['acceptance'][0]);second['id']='T1-B'
        task['acceptance'].append(second);task['coverage'].append({'criterion':'T1-B','test':0})
        self.save();original=read(self.path);session=self.base/'failed';session.mkdir()
        frozen=session/'task-state.json';task=plans.select(self.path,'T1')
        tasks.begin(self.root,['.'],task,frozen,session/'shadow')
        packet={'remaining':original['tasks'],'plan':str(self.path),'reason':'acceptance_failed',
            'completed':[],'current_snapshot':original['snapshot'],'session':str(session)}
        candidate=copy.deepcopy(original);candidate['tasks'][0]['acceptance'].reverse()
        attach_lineage(candidate,packet)
        self.assertEqual(candidate['tasks'][0]['baseline'],str(frozen))

    def test_later_task_regression_revokes_earlier_pass(self):
        """A valid local gate cannot conceal a previously accepted behavior breaking."""
        second = copy.deepcopy(self.plan['tasks'][0]); second.update(id='T2', depends_on=['T1'], files=['other.py','slug.py'])
        second['tests'] = [[sys.executable, '-c', "from other import slugify; assert slugify('ABC') == 'abc'"]]
        self.plan['tasks'].append(second); self.save()
        def regress(command, folder, timeout):
            result = self.fake(command, folder, timeout)
            if command[command.index('--todo')+1] == 'T2':
                self.source.write_text(self.source.read_text().replace('.lower()', ''))
                state = Path(result['session']) / 'task-state.json'
                shadow.refresh(self.root, ['.'], Path(result['session']) / 'shadow')
                tasks.run_tests(state)
            return result
        self.assertEqual(execute(self.root, self.path, self.folder, regress), REPLAN_EXIT)
        self.assertEqual(read(self.folder/'replan-request.json')['reason'], 'previous_acceptance_regressed')
        self.assertEqual([t['status'] for t in read(self.path)['tasks']], ['todo','todo'])


if __name__ == '__main__':
    unittest.main()
