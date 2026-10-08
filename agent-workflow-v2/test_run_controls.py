"""Restart binding, user prompt persistence and ownership never bypass task gates."""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from run_controls import Controls
from runner_process import read,save
from task_instructions import current,prompt_file,instruction_file
from plan_runner import command


class RunControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.run=self.base/'run-1';self.run.mkdir()
        self.root=self.base/'project';self.root.mkdir()
        self.task={'id':'T1','goal':'Normalize text','steps':['Inspect','Test'],'status':'todo'}
        self.plan=self.base/'plan.json';save(self.plan,{'tasks':[self.task]})
        self.state={'project':str(self.root),'plan':str(self.plan),'status':'interrupted','current_todo':'T1','attempt_folder':str(self.run/'01-T1')}
        save(self.run/'state.json',self.state)
        save(self.run/'recovery-state.json',{'project':str(self.root),'original_plan':str(self.plan),'status':'executing'})
        monitor=Mock();monitor.selected.return_value=self.run;self.control=Controls(monitor)
        self.control.launch=Mock(return_value=SimpleNamespace(pid=12345))

    def submit(self,mode='append',prompt='Check an empty input.'):
        binding=self.control.view();result=self.control.restart({'revision':binding['revision'],'mode':mode,'prompt':prompt})
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            row=read(self.run/'ui-control.json')
            if row.get('status')!='stopping':return row
            time.sleep(.01)
        self.fail('Restart did not finish')

    def test_append_uses_fresh_native_resume_and_retains_original_plan(self):
        before=self.plan.read_bytes();row=self.submit()
        self.assertEqual(row['status'],'starting');self.assertEqual(before,self.plan.read_bytes())
        prompt=current(self.run,self.task);self.assertIn('Normalize text',prompt);self.assertIn('Check an empty input.',prompt)
        argv=self.control.launch.call_args.args[0]
        self.assertEqual(argv[1:3],['resume',str(self.root)]);self.assertIn(str(self.plan),argv)
        self.assertEqual(len(list((self.run/'task-instructions').glob('T1-*.json'))),1)
        file=prompt_file(self.run,self.task);self.assertIn('Preserve the frozen',Path(file).read_text())
        built=command(self.root,self.plan,self.task,file,instruction_file(self.run,self.task))
        self.assertIn('--task-instructions-file',built)

    def test_replace_edits_strategy_without_altering_frozen_plan(self):
        self.submit('replace','Use the supplied requirements; start with the boundary tests.')
        self.assertEqual(current(self.run,self.task),'Use the supplied requirements; start with the boundary tests.')
        self.assertEqual(read(self.plan)['tasks'][0],self.task)

    def test_stale_attempt_cannot_receive_edited_prompt(self):
        revision=self.control.view()['revision'];save(self.run/'state.json',{**self.state,'attempt_folder':'different'})
        with self.assertRaisesRegex(ValueError,'active task changed'):
            self.control.restart({'revision':revision,'mode':'append','prompt':'Instruction'})
        self.control.launch.assert_not_called()

    def test_oversize_and_unknown_fields_do_not_create_requests(self):
        for extra in [{'prompt':'x'*16001},{'mode':'shell'},{'command':'arbitrary'}]:
            with self.assertRaises(ValueError):self.control.restart({'revision':self.control.view()['revision'],'mode':'append','prompt':'hello',**extra})
        self.assertFalse((self.run/'ui-control.json').exists())

    def test_unverified_running_pid_is_never_signalled(self):
        save(self.run/'state.json',{**self.state,'status':'running'})
        save(self.run/'coordinator-process.json',{'pid':42,'identity':'previous','project':str(self.root)})
        with patch('run_controls.identity',return_value='different'),patch('run_controls.os.kill') as kill:
            row=self.submit()
        self.assertEqual(row['status'],'failed');kill.assert_not_called();self.control.launch.assert_not_called()

    def test_verified_stop_precedes_instruction_and_restart(self):
        save(self.run/'state.json',{**self.state,'status':'running'})
        save(self.run/'coordinator-process.json',{'pid':42,'identity':'owned','project':str(self.root)})
        with patch('run_controls.identity',side_effect=['owned','']),patch('run_controls.os.kill',side_effect=lambda *_:save(self.run/'state.json',self.state)) as kill:
            self.assertEqual(self.submit()['status'],'starting')
        kill.assert_called_once();self.control.launch.assert_called_once()

    def test_task_change_while_stopping_does_not_apply_to_next_task(self):
        save(self.run/'state.json',{**self.state,'status':'running'})
        save(self.run/'coordinator-process.json',{'pid':42,'identity':'owned','project':str(self.root)})
        with patch('run_controls.identity',side_effect=['owned','']),patch('run_controls.os.kill',side_effect=lambda *_:save(self.run/'state.json',{**self.state,'current_todo':'T2'})):
            self.assertEqual(self.submit()['status'],'failed')
        self.assertFalse((self.run/'task-instructions').exists());self.control.launch.assert_not_called()

    def test_controls_exclude_planning_and_completed_tasks(self):
        save(self.run/'state.json',{**self.state,'workflow_phase':'planning'})
        self.assertFalse(self.control.view()['available'])
        save(self.run/'state.json',self.state);save(self.plan,{'tasks':[{**self.task,'status':'done'}]})
        self.assertFalse(self.control.view()['available'])

    def test_startup_failure_is_reported_and_cannot_be_called_started(self):
        self.submit()
        with patch('run_controls.identity',return_value=''):
            self.assertEqual(self.control.view()['request']['status'],'failed')

    def test_duplicate_submission_cannot_launch_a_second_worker(self):
        revision=self.control.view()['revision'];self.submit()
        with self.assertRaisesRegex(ValueError,'already in progress'):
            self.control.restart({'revision':revision,'mode':'append','prompt':'Another instruction'})
        self.control.launch.assert_called_once()


if __name__=='__main__':unittest.main()
