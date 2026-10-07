"""Future worker budgets survive a smaller reviewer session without implicit clamping."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import plans
import profiles
from plan_draft import bind,restore
from project_map import scan
from test_plan_runner import todo
from test_profiles import options


class SessionBudgetScopeTests(unittest.TestCase):
    def test_review_save_and_worker_resolution_preserve_larger_or_smaller_task_budgets(self):
        for output,thinking,effort in [(32768,8192,'xhigh'),(8192,2048,'low')]:
            with self.subTest(output=output),tempfile.TemporaryDirectory() as directory:
                base=Path(directory);root=base/'project';root.mkdir()
                task=todo();task['tests']=[['python3','-m','unittest']]
                task['context'].update(window_tokens=98304,max_input_tokens=40960,
                    max_output_tokens=output,reasoning_budget_tokens=thinking,reasoning_effort=effort)
                proposal={'plan_version':3,'goal':'Normalize text','architecture':'Pure function','tasks':[task]}
                source=base/'draft.json';source.write_text(json.dumps(proposal))
                bound=base/'bound.json';bind(root,source,bound,scan(root,['.'])['snapshot'],target='T1')
                controls={'QWEN_WORKFLOW_ROLE':'architect','QWEN_WORKFLOW_INPUT_BUDGET':'57344',
                    'QWEN_WORKFLOW_OUTPUT_BUDGET':'16384','QWEN_WORKFLOW_REASONING_BUDGET_TOKENS':'1024',
                    'QWEN_WORKFLOW_REASONING':'medium'}
                with patch.dict(os.environ,controls):
                    accepted=restore(root,['.'],bound,{'unchanged':True})
                    output_path=base/'reviewed.json';plans.save(root,['.'],accepted,output_path)
                    saved=json.loads(output_path.read_text())['tasks'][0]
                    self.assertEqual(saved['context'],task['context'])
                    args=options(profile='mtplx-quality',role='code')
                    resolved=profiles.resolve(args,saved,profiles.apply_identity(args))
                self.assertEqual((resolved['output_tokens'],resolved['reasoning_budget'],resolved['reasoning']),
                                 (output,thinking,effort))
                self.assertEqual(resolved['input_tokens'],40960)

    def test_independent_future_budgets_still_obey_native_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=todo();task['tests']=[['python3','-m','unittest']]
            for values in ({'max_output_tokens':49152},{'reasoning_budget_tokens':8192},
                           {'window_tokens':32768,'max_input_tokens':24576}):
                invalid=copy.deepcopy(task);invalid['context'].update(values)
                with self.subTest(values=values),self.assertRaises(ValueError):plans.validate_task(root,invalid)
