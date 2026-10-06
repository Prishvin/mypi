"""Exercise resumption with real fixtures, partial code and preserved baselines."""
import copy
import sys
import unittest
import test_plan_runner as runner_fixtures
from plan_runner import execute, REPLAN_EXIT
from runner_process import read, save


class ResumeTests(unittest.TestCase):
    setUp = runner_fixtures.RunnerTests.setUp
    save = runner_fixtures.RunnerTests.save
    fake = runner_fixtures.RunnerTests.fake
    def prepare_two_tasks(self):
        second = copy.deepcopy(self.plan['tasks'][0])
        second.update(id='T2', depends_on=['T1'], files=['other.py'])
        second['context'].update(interfaces=['other.py'])
        second['tests'] = [[sys.executable, '-c', "from other import slugify; assert slugify('ABC') == 'abc'"]]
        self.plan['tasks'].append(second)
        self.save()

    def interrupt_second(self, command, folder, timeout):
        result = self.fake(command, folder, timeout, correct=command[command.index('--todo') + 1] == 'T1')
        save(folder / 'session.json', {'session': result['session']})
        if command[command.index('--todo') + 1] == 'T2':
            raise KeyboardInterrupt
        return result

    def test_explicit_resume_preserves_first_task_and_continues_partial_second_task(self):
        self.prepare_two_tasks()
        self.assertEqual(execute(self.root, self.path, self.folder, self.interrupt_second), 130)
        self.assertEqual(read(self.folder / 'state.json')['status'], 'interrupted')
        self.assertEqual([t['status'] for t in read(self.path)['tasks']], ['done', 'todo'])
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake), 130)
        baseline = read(self.path)['tasks'][1]['baseline']
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake, resume=True), 0)
        self.assertEqual(self.calls, ['T1', 'T2', 'T2'])
        self.assertEqual(read(self.path)['tasks'][1]['baseline'], baseline)
        brief = (self.folder / 'resume-brief.txt').read_text()
        self.assertIn('accepted_todos_do_not_repeat', brief)
        self.assertIn('other.py', brief)
        self.assertNotIn('return text', brief)

    def test_source_changes_after_interruption_require_replanning(self):
        self.prepare_two_tasks()
        execute(self.root, self.path, self.folder, self.interrupt_second)
        (self.root / 'other.py').write_text('def changed():\n    return 3\n')
        with self.assertRaisesRegex(ValueError, 'changed after interruption'):
            execute(self.root, self.path, self.folder, self.fake, resume=True)
        self.assertEqual(self.calls, ['T1', 'T2'])

    def test_accepted_regression_is_checked_before_resumed_inference(self):
        self.prepare_two_tasks()
        execute(self.root, self.path, self.folder, self.interrupt_second)
        self.source.write_text(self.source.read_text().replace('.lower()', ''))
        with self.assertRaisesRegex(ValueError, 'Accepted behavior changed'):
            execute(self.root, self.path, self.folder, self.fake, resume=True)
        self.assertEqual(self.calls, ['T1', 'T2'])

    def test_actual_failed_acceptance_cannot_use_resume_to_bypass_replanning(self):
        self.save()
        self.assertEqual(execute(self.root, self.path, self.folder,
                                lambda *args: self.fake(*args, correct=False)), REPLAN_EXIT)
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake, resume=True), REPLAN_EXIT)
        self.assertEqual(self.calls, ['T1'])

    def test_running_crash_checkpoint_can_resume_partial_work_with_frozen_evidence(self):
        self.prepare_two_tasks()
        execute(self.root, self.path, self.folder, self.interrupt_second)
        state = read(self.folder / 'state.json')
        state['status'] = 'running'
        save(self.folder / 'state.json', state)
        self.assertEqual(execute(self.root, self.path, self.folder, self.fake, resume=True), 0)
        self.assertEqual(self.calls, ['T1', 'T2', 'T2'])

    def test_partial_edit_outside_scope_cannot_be_resumed(self):
        self.prepare_two_tasks()
        def outside(command, folder, timeout):
            if command[command.index('--todo') + 1] == 'T2':
                result = self.fake(command, folder, timeout, correct=False)
                save(folder / 'session.json', {'session': result['session']})
                self.source.write_text(self.source.read_text() + '\n# Unauthorized edit\n')
                raise KeyboardInterrupt
            return self.interrupt_second(command, folder, timeout)
        execute(self.root, self.path, self.folder, outside)
        with self.assertRaisesRegex(ValueError, 'outside task scope'):
            execute(self.root, self.path, self.folder, self.fake, resume=True)


if __name__ == '__main__':
    import unittest
    unittest.main()
