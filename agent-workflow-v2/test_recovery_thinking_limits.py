"""Recovery depth is phase-local and must not alter cloud or future executor caps."""
import unittest
from planning_limits import arguments, limits


class RecoveryThinkingTests(unittest.TestCase):
    def test_qwen_recovery_has_bounded_extra_reasoning_and_sufficient_output_space(self):
        budget = limits('qwen', 'recovery'); argv = arguments('qwen', 'recovery')
        self.assertEqual(argv[argv.index('--reasoning-budget') + 1], '4096')
        self.assertEqual(budget['reasoning'], 'medium')
        self.assertGreaterEqual(budget['output'] - budget['reasoning_budget'], 2048)
        self.assertLessEqual(budget['input'] + budget['output'] + 8192, budget['context'])

    def test_normal_review_and_cloud_choices_remain_independent(self):
        argv = arguments('qwen', 'review')
        self.assertEqual(argv[argv.index('--reasoning-budget') + 1], '1024')
        cloud = arguments('chatgpt', 'recovery')
        self.assertNotIn('--reasoning-budget', cloud)
        self.assertEqual(cloud[cloud.index('--reasoning') + 1], 'xhigh')


if __name__ == '__main__':
    unittest.main()
