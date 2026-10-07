"""Planning stages must not receive contradictory full-plan save instructions."""
import unittest
from task_prompts import planning


class PlanningPromptTests(unittest.TestCase):
    def test_new_draft_keeps_full_contract_and_selected_capacity(self):
        text=planning('Build a small utility',{'context':98304})
        self.assertIn('Build a small utility',text)
        self.assertIn('98304 tokens',text)
        self.assertIn('Save exactly one object with plan_version: 3',text)

    def test_review_preserves_exact_packet_without_wrapping_it_as_new_development(self):
        request='REVIEW INPUT: {"current_task":{"id":"T1"},"literal":"{{CONTEXT}}"}'
        for mode,contract in [('repair','sparse task_updates'),('coverage','coverage_plan only')]:
            with self.subTest(mode=mode):
                text=planning(request,{'context':272000},mode)
                self.assertTrue(text.endswith(request))
                self.assertIn('272000 tokens',text)
                self.assertIn(contract,text)
                self.assertNotIn('Save exactly one object with plan_version: 3',text)
                self.assertNotIn('Plan this authorized change',text)
        with self.assertRaises(ValueError):planning(request,{'context':98304},'invalid')
