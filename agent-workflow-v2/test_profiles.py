"""Verify profile isolation, precedence and usable per-task response reserves."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import subprocess
from unittest.mock import patch
import launch
import profiles
from plans import save, validate_context
from test_plans import example_task


def options(**overrides):
    """Build CLI options without contacting a model or using account credentials."""
    result = dict(profile=None, model=None, planner=None, executor=None, planner_model=None,
                  role='code', context=None, task_size=None, input_tokens=None, output_tokens=None,
                  thinking=None, reasoning=None, reasoning_budget=None, stop_after_pass=None,
                  task=None, plan=None, todo=None, briefs=None, prefix=[], json=True,
                  prompt=None, progress_seconds=30)
    result.update(overrides)
    return SimpleNamespace(**result)


class ProfileTests(unittest.TestCase):
    """Exercise independent model/profile and task choices with real session preparation."""
    def resolve(self, task=None, **kwargs):
        """Resolve a requested private profile and one frozen task recipe."""
        args = options(**kwargs)
        return args, profiles.resolve(args, task or {}, profiles.apply_identity(args))

    def test_compaction_precedes_serialized_admission_with_envelope_headroom(self):
        import math
        from token_budget import ADMISSION_FACTOR, TEMPLATE_RESERVE
        with tempfile.TemporaryDirectory() as folder,patch('launch.server_config.load',return_value={
                'model':'mtplx-quality','url':'http://localhost:8000'}):
            folder=Path(folder)
            for budget in [16384,24576,32768,57344]:
                launch.configure(folder,'quality',98304)
                launch.tune_context(folder,budget,8192)
                settings=json.loads((folder/'settings.json').read_text())
                trigger=98304-settings['compaction']['reserveTokens']
                self.assertLessEqual(math.ceil((trigger+4096)*ADMISSION_FACTOR)+TEMPLATE_RESERVE,budget)
                self.assertEqual(settings['compaction']['keepRecentTokens'],min(4000,budget//3))
                model=json.loads((folder/'models.json').read_text())['providers']['local-qwen-workflow']['models'][0]
                self.assertEqual((model['contextWindow'],model['maxTokens']),(98304,8192))
                if budget==32768:
                    self.assertLess(trigger,26513) # observed Linux payload that overflowed admission

    def test_all_combinations_and_cloud_caps(self):
        """Both roles are configurable for all five planner/executor combinations."""
        self.assertEqual(len(profiles.catalog()['profiles']), 11)
        for name in profiles.catalog()['profiles']:
            for role in ['architect', 'code']:
                args, setting = self.resolve(profile=name, role=role)
                cloud = args.planner == 'chatgpt' if role == 'architect' else args.executor == 'chatgpt'
                self.assertEqual(setting['context'],272000 if cloud else 98304)
                self.assertEqual(setting['output_tokens'], 32768 if role == 'architect' else 16384)
                cloud = args.planner == 'chatgpt' if role == 'architect' else args.executor == 'chatgpt'
                self.assertEqual(setting['reasoning_budget'], None if cloud or args.model == 'gemma' else 4096)
                self.assertEqual(setting['input_tokens'], (196608 if cloud else 57344) if role == 'architect' else 24576)
                self.assertEqual(setting['stop_after_pass'], role == 'code' and not cloud)

    def test_task_budget_and_cli_precedence(self):
        """Reviewed task values override profile defaults; explicit CLI overrides the task."""
        task = {'context': {'preset': 'small', 'max_input_tokens': 12000,
                            'max_output_tokens': 8192, 'reasoning_budget_tokens': 2048}}
        _, current = self.resolve(task, profile='local-flash')
        self.assertEqual((current['input_tokens'], current['output_tokens'], current['reasoning_budget']),
                         (12000, 8192, 2048))
        _, forced = self.resolve(task, profile='local-flash', task_size='standard', output_tokens=12288)
        self.assertEqual((forced['input_tokens'], forced['output_tokens'], forced['reasoning_budget']),
                         (24576, 12288, 4096))

    def test_presets_fit_96k_and_reject_insufficient_windows(self):
        """Input-heavy presets leave template/output room without silently resizing."""
        for model in ['local-27b','local-flash']:
            for size in ['small','standard','large']:
                _, setting=self.resolve(profile=model,task_size=size,context=98304)
                self.assertGreater(setting['input_tokens'],setting['output_tokens'])
                self.assertLessEqual(setting['input_tokens']+setting['output_tokens']+2048,98304)
            for size in ['small','standard']:
                self.resolve(profile=model,task_size=size,context=65536)
            with self.assertRaisesRegex(ValueError,'exceeds'):
                self.resolve(profile=model,task_size='large',context=65536)

    def test_independent_cli_input_output_and_thinking_overrides(self):
        """A selected preset does not force a fixed input/output ratio."""
        _, setting=self.resolve(profile='local-27b',task_size='standard',input_tokens=49152,
                               output_tokens=8192,reasoning_budget=2048)
        self.assertEqual((setting['input_tokens'],setting['output_tokens'],setting['reasoning_budget']),
                         (49152,8192,2048))

    def test_small_client_window_and_model_ceiling(self):
        """A 32k task needs explicit lower input; 27B cannot request Flash-only 128k."""
        _, small = self.resolve(profile='local-27b', task_size='small', context=65536)
        self.assertEqual(small['output_tokens'], 8192)
        _, reduced = self.resolve(profile='local-27b', task_size='small', context=32768)
        self.assertEqual(reduced['input_tokens']+reduced['output_tokens']+8192,32768)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            self.resolve(profile='local-27b', task_size='small', context=32768, input_tokens=22528)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            self.resolve(profile='local-27b', task_size='large', context=32768)
        with self.assertRaisesRegex(ValueError, 'ceiling'):
            self.resolve({'context': {'window_tokens': 131072}}, profile='local-27b')
        _, large = self.resolve(profile='local-flash', context=131072)
        self.assertEqual(large['context'], 131072)

    def test_thinking_reserve_and_off_override(self):
        """Thinking caps leave room for actual edits and cannot be applied to thinking-off."""
        with self.assertRaisesRegex(ValueError, 'leave at least'):
            self.resolve(profile='local-flash', output_tokens=8192, reasoning_budget=8192)
        _, mechanical = self.resolve(profile='local-flash', task_size='small', thinking='off')
        self.assertIsNone(mechanical['reasoning_budget'])
        with self.assertRaisesRegex(ValueError, 'thinking-on'):
            self.resolve(profile='local-flash', thinking='off', reasoning_budget=1024)
        with self.assertRaises(ValueError):
            self.resolve(profile='chatgpt-baseline', reasoning_budget=1024)

    def test_legacy_invocations_keep_their_defaults(self):
        """Invocations without a profile retain thinking-off and historical task budgets."""
        _, legacy = self.resolve(example_task())
        self.assertEqual((legacy['context'], legacy['thinking'], legacy['output_tokens']),
                         (65536, 'off', 4096))
        self.assertFalse(legacy['stop_after_pass'])

    def test_prepare_persists_effective_caps_and_granular_prompt(self):
        """Preparing either role uses private settings and saves exactly the selected todo."""
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            repo = base / 'repo'; repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            for name in ('qwen-rules.txt','architect-rules.txt','architect-recovery-rules.txt','research-rules.txt','intake-rules.txt','reviewer-rules.txt','memory-rules.txt'):
                (base/name).write_text('Private test rules')
            (repo / 'slug.py').write_text('def slugify(text):\n    """Make a slug."""\n    return text\n')
            task = base / 'task.json'; task.write_text(json.dumps(example_task()))
            (base / 'sessions').mkdir()
            tokenizer_path = launch.BASE / 'qwen-tokenizer.json'
            with patch.object(launch, 'BASE', base), patch.object(launch, 'model_tokenizer', return_value=tokenizer_path):
                prepared = launch.prepare(options(profile='local-flash', project=repo,
                                                  task=task, task_size='small', context=65536))
                model = json.loads((Path(prepared['session'])/'pi-config/models.json').read_text())
                descriptor = model['providers']['local-qwen-workflow']['models'][0]
                self.assertEqual((descriptor['contextWindow'], descriptor['maxTokens']), (65536, 8192))
                self.assertEqual(prepared['input_budget'],16384)
                self.assertEqual(prepared['reasoning_budget_tokens'], 2048)
                self.assertEqual(prepared['profile'], 'local-flash')
                self.assertIn('steps', launch.prepare(options(profile='local-flash', project=repo,
                                                            role='architect'))['command'][-1])
                source=base/'proposal.json'
                source.write_text(json.dumps({'plan_version':3,'goal':'Utility','architecture':'Pure API',
                                              'tasks':[example_task()]}))
                for mode in ({'refine_task':'T1'},{'plan_coverage':True},{}):
                    reviewed=launch.prepare(options(profile='local-flash',project=repo,role='architect',
                        plan_draft=source,prompt='Exact review packet',**mode))
                    prompt=reviewed['command'][-1]
                    self.assertIn('Exact review packet',prompt)
                    selected_tools=reviewed['command'][reviewed['command'].index('--tools')+1].split(',')
                    self.assertEqual('plan_child_store' in selected_tools,bool(mode.get('refine_task')))
                    self.assertNotIn('Save exactly one object with plan_version: 3',prompt)
                    self.assertIn('coverage_plan only' if mode.get('plan_coverage') else 'flat changed fields' if mode.get('refine_task') else 'sparse task_updates',prompt)
                evidence=base/'failure.json'
                from project_map import scan
                original=json.loads(source.read_text());original['project']=str(repo.resolve())
                source.write_text(json.dumps(original))
                evidence.write_text(json.dumps({'project':str(repo.resolve()),'plan':str(source),
                    'current_snapshot':scan(repo,['.'])['snapshot']}))
                recovered=launch.prepare(options(profile='local-flash',project=repo,role='architect',
                    replan_evidence=evidence,prompt='Measured failure packet'))
                prompt=recovered['command'][-1]
                self.assertIn('failure_analysis and flat changed fields',prompt)
                self.assertNotIn('Save exactly one object with plan_version: 3',prompt)
                pinned=json.loads(Path(recovered['replan_evidence']).read_text())
                from plan_draft import digest
                self.assertEqual(pinned['recovery_plan_sha256'],digest(original))
                self.assertTrue((Path(recovered['runtime'])/'architect-recovery-rules.txt').is_file())


    def test_profile_path_traversal_rejected(self):
        """Named profiles cannot read credentials or arbitrary files."""
        with self.assertRaises(ValueError):
            profiles.load('../planner-config/auth')


class GranularPlanTests(unittest.TestCase):
    """Ensure modern plans contain actionable atomic steps and honest test contracts."""
    def test_56k_plan_input_is_accepted_only_with_sufficient_context(self):
        """Planning can hand off more input while checking the output and window sum."""
        with tempfile.TemporaryDirectory() as folder:
            task=example_task()
            task['context'].update(max_input_tokens=57344,max_output_tokens=32768,window_tokens=98304)
            validate_context(Path(folder),task)
            task['context']['window_tokens']=65536
            with self.assertRaisesRegex(ValueError,'exceed'):
                validate_context(Path(folder),task)
            task['context'].update(window_tokens=98304,max_input_tokens=57345)
            with self.assertRaisesRegex(ValueError,'57344'):
                validate_context(Path(folder),task)

    def test_v2_rejects_missing_steps_and_excess_thinking(self):
        """The plan gate enforces v2 granularity and preserves old v1 plans."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root/'slug.py').write_text('def slugify(text):\n    """Make a slug."""\n    return text\n')
            task = example_task()
            plan = {'plan_version': 2, 'goal':'Fix slug', 'architecture':'Pure logic', 'tasks':[task]}
            with self.assertRaisesRegex(ValueError, 'steps'):
                save(root, ['.'], plan, root/'plan.json')
            task.update(steps=['Normalize separators', 'Verify edge cases'], assumptions=[],
                        test_strategy='Assert repeated, empty and edge separators', estimated_changed_lines=30)
            task['context']['reasoning_budget_tokens'] = 4096
            with self.assertRaisesRegex(ValueError, 'Thinking cap'):
                save(root, ['.'], plan, root/'plan.json')
            task['context']['reasoning_budget_tokens'] = 1024
            save(root, ['.'], plan, root/'plan.json')
            self.assertEqual(json.loads((root/'plan.json').read_text())['plan_version'], 2)
