"""Command-line stage selection without launching model servers in tests."""
import importlib.util
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
SPEC=importlib.util.spec_from_file_location('pi_local_private',Path(__file__).resolve().parent.parent/'pi_local.py')
pi_local=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(pi_local)


class CliTests(unittest.TestCase):
    def test_final_review_runs_after_success_but_never_after_failed_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            argv=['execute',folder,folder+'-plan.json','--run-dir',folder+'-run']
            with (patch.object(pi_local,'initialize'),patch.object(pi_local,'start'),
                  patch('plan_runner.execute',return_value=20),patch('review_service.review') as review):
                self.assertEqual(pi_local.main(argv),20);review.assert_not_called()
            with (patch.object(pi_local,'initialize'),patch.object(pi_local,'start'),
                  patch('plan_runner.execute',return_value=0),
                  patch('review_service.review',return_value={'passed':True,'verdict':'followup'}) as review):
                self.assertEqual(pi_local.main(argv),0);review.assert_called_once()
    def test_pending_question_returns_two_without_starting_local_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'project'; output=Path(folder)/'plan.json'
            with (patch.object(pi_local,'initialize'),patch.object(pi_local,'start') as start,
                 patch('planning_service.create',return_value={'passed':False,'stage':'awaiting_clarification'}) as create):
                code=pi_local.main(['plan',str(root),'Ambiguous request','--out',str(output),'--non-interactive','--planner','chatgpt'])
            self.assertEqual(code,2);start.assert_not_called()
            self.assertEqual(create.call_args.kwargs['clarifier'],'auto')
            self.assertEqual(create.call_args.kwargs['interactive'],False)

    def test_qwen_override_starts_backend_and_skill_listing_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(pi_local,'initialize'),patch.object(pi_local,'start') as start,
                 patch('planning_service.create',return_value={'passed':True})):
                self.assertEqual(pi_local.main(['plan',folder,'Request','--out',folder+'-plan.json','--clarifier','qwen']),0)
            start.assert_called_once()
        with patch.object(pi_local,'initialize') as initialize,patch.object(pi_local,'start') as start:
            self.assertEqual(pi_local.main(['skills']),0)
        initialize.assert_not_called();start.assert_not_called()


if __name__=='__main__': unittest.main()
