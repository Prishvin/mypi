"""Repair limits survive saved low caps without leaking into ordinary tasks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import launch
import profiles
from test_profiles import options


class RepairBudgets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = self.root/'plan.json'
        self.plan.write_text(json.dumps({'recovery_patch': {'todo': 'failed'}}))

    def resolve(self, task=None, **overrides):
        args = options(profile='mtplx-quality', project=self.root, **overrides)
        return profiles.resolve(args, task or {}, profiles.apply_identity(args))

    def test_failure_reviewer_ignores_small_saved_default(self):
        with patch('thinking_caps.load', return_value=1024):
            settings = self.resolve(role='architect', replan_evidence=self.root/'failure.json')
        self.assertEqual(settings['reasoning_budget'], 8192)
        self.assertEqual(settings['repair_budget_policy']['requested']['reasoning_budget'], 1024)

    def test_only_selected_failed_todo_receives_floor_and_output_reserve(self):
        task = {'context': {'thinking': 'off', 'reasoning_budget_tokens': 1024,
                           'max_output_tokens': 4096, 'max_input_tokens': 20480,
                           'window_tokens': 32768}}
        settings = self.resolve(task, plan=self.plan, todo='failed')
        self.assertEqual((settings['thinking'], settings['reasoning_budget']), ('on', 8192))
        self.assertEqual((settings['output_tokens'], settings['input_tokens'], settings['context']),
                         (10240, 20480, 65536))
        normal = self.resolve(task, plan=self.plan, todo='later')
        self.assertEqual((normal['thinking'], normal['output_tokens']), ('off', 4096))
        self.assertNotIn('repair_budget_policy', normal)

    def test_higher_cap_and_explicit_uncapped_are_preserved(self):
        for cap in (12288, 0):
            setting = self.resolve(plan=self.plan, todo='failed', reasoning_budget=cap,
                                   output_tokens=16384)
            self.assertEqual(setting['reasoning_budget'], cap)
        setting = self.resolve(plan=self.plan, todo='failed', uncapped_thinking=True)
        self.assertIsNone(setting['reasoning_budget'])

    def test_normal_and_cloud_roles_keep_their_controls(self):
        normal = self.resolve(role='architect')
        self.assertEqual(normal['reasoning_budget'], 4096)
        cloud = self.resolve(role='architect', planner='chatgpt', replan_evidence='evidence')
        self.assertIsNone(cloud['reasoning_budget'])
        self.assertNotIn('repair_budget_policy', cloud)
        manual=self.resolve(task_instructions_file='user-request.json',thinking='off')
        self.assertEqual((manual['thinking'],manual['reasoning_budget']),('on',8192))

    def test_draft_repair_but_not_regular_refinement_gets_floor(self):
        for flags, cap in [({},8192), ({'refine_task':'T1'},4096), ({'plan_coverage':True},4096)]:
            setting=self.resolve(role='architect',plan_draft='draft',**flags)
            self.assertEqual(setting['reasoning_budget'],cap)

    def test_impossible_output_or_window_fails_without_shrinking_input(self):
        with self.assertRaisesRegex(ValueError, 'model window'):
            self.resolve(plan=self.plan,todo='failed',input_tokens=90000,output_tokens=10240)
        with self.assertRaisesRegex(ValueError, 'output_tokens'):
            self.resolve(plan=self.plan,todo='failed',reasoning_budget=32768)

    def test_native_preparation_reports_same_cap_in_prompt_state_and_launch(self):
        from test_plans import example_task
        task=example_task();task.update(id='failed',status='todo',context={**task.get('context',{}),
            'max_input_tokens':24576,'max_output_tokens':8192,'window_tokens':65536,
            'thinking':'on','reasoning_budget_tokens':1024})
        self.plan.write_text(json.dumps({'tasks':[task],'recovery_patch':{'todo':'failed'}}))
        project=self.root/'project';project.mkdir()
        instruction=self.root/'instruction.json';instruction.write_text(json.dumps({'todo':'failed','prompt':'Include the empty-input boundary case.'}))
        with patch.object(launch,'BASE',self.root),patch('launch.server_config.load',return_value={
                'url':'http://localhost:8000','model':'mtplx-quality'}):
            # Preserve actual runtime source while isolating generated sessions.
            original=launch.runtime.capture
            with patch('launch.runtime.capture',side_effect=lambda base,session:original(Path(launch.__file__).parent,session)):
                result=launch.prepare(options(profile='mtplx-quality',project=project,
                                              plan=self.plan,todo='failed',task_instructions_file=instruction))
        state=json.loads(Path(result['state']).read_text())
        self.assertEqual(result['reasoning_budget_tokens'],8192)
        self.assertEqual(state['task']['context']['reasoning_budget_tokens'],8192)
        self.assertEqual(result['output_budget'],10240)
        self.assertEqual(state['task']['user_instructions'],'Include the empty-input boundary case.')


if __name__ == '__main__': unittest.main()
