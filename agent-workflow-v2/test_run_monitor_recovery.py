"""A failure review must retain implementation evidence without mixing project runs."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from run_monitor import RunMonitor, read
from run_monitor_recovery import implementation


class RecoveryQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.owner = self.root / 'run-1'
        self.stage = self.owner / 'repair-1.stages'
        tasks = [{'id': name, 'files': [], 'status': status, 'depends_on': deps}
                 for name, status, deps in [('A', 'done', []), ('B', 'todo', ['A']), ('C', 'todo', ['B'])]]
        self.plan = self.save('plan.json', {'project': str(self.root), 'tasks': tasks})
        self.session = self.root / 'session'
        self.save('session/task-state.json', {'evidence': {'results': [{'exit_code': 1}]}})
        self.save('run-1/02-B/session.json', {'session': str(self.session), 'prompt': 'SECRET'})
        self.save('run-1/state.json', {'project': str(self.root), 'plan': str(self.plan),
            'status': 'needs_replan', 'current_todo': 'B', 'reason': 'context_budget_exceeded',
            'updated_epoch': 100, 'attempt_started_epoch': 50,
            'attempt_folder': str(self.owner / '02-B'),
            'attempts': [{'todo': 'B', 'wall_seconds': 50, 'gate': {'passed': False},
                          'metrics': {'output_tokens_sum': 123}}]})
        self.recovery = {'project': str(self.root), 'current_run': str(self.owner),
            'current_plan': str(self.plan), 'status': 'reviewing',
            'repairs': [{'plan': str(self.owner / 'repair-1.json')}]}
        self.save('run-1/recovery-state.json', self.recovery)
        queue = self.save('run-1/repair-1.stages/queue.json', {'tasks': [{'id': 'FAILURE-REVIEW', 'files': []}]})
        self.state = {'project': str(self.root), 'plan': str(queue), 'status': 'running',
            'workflow_phase': 'planning', 'current_todo': 'FAILURE-REVIEW'}
        self.save('run-1/repair-1.stages/state.json', self.state)
        self.monitor = RunMonitor(self.root, backend='http://127.0.0.1:1')
        self.monitor.native_at = time.monotonic()
        self.monitor.native = {'available': False}

    def save(self, name, data):
        """Write bounded deterministic evidence fixtures without invoking a model."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def test_review_retains_real_statuses_tests_metrics_and_stopped_clock(self):
        with patch.object(self.monitor, 'selected', return_value=self.stage):
            result = self.monitor.snapshot()
        self.assertEqual(result['current_todo'], 'FAILURE-REVIEW')
        self.assertEqual((result['accepted'], result['total']), (0, 1))
        rows = result['implementation_tasks']
        self.assertEqual([row['status'] for row in rows], ['Accepted', 'Failed', 'Blocked'])
        self.assertTrue(all(row['implementation'] and not row.get('preview') for row in rows))
        self.assertEqual(rows[1]['elapsed_seconds'], 50)
        self.assertEqual(rows[1]['test_results'], [{'exit_code': 1}])
        self.assertEqual(rows[1]['attempts'][0]['metrics']['output_tokens_sum'], 123)
        self.assertEqual(result['implementation_state'], {'run': 'run-1', 'status': 'needs_replan',
            'current_todo': 'B', 'reason': 'context_budget_exceeded', 'accepted': 1, 'total': 3})
        self.assertNotIn('SECRET', json.dumps(result))

    def test_nested_repair_run_retains_completed_lineage(self):
        repaired = self.save('run-1/repair-0.json', {'project': str(self.root),
            'tasks': [{'id': 'B', 'files': []}],
            'replan_lineage': {'completed': [{'id': 'A', 'files': [], 'status': 'done'}]}})
        self.save('run-1/repair-0/state.json', {'project': str(self.root), 'plan': str(repaired),
            'status': 'needs_replan', 'current_todo': 'B'})
        self.recovery.update(current_run=str(self.owner / 'repair-0'), current_plan=str(repaired))
        self.save('run-1/recovery-state.json', self.recovery)
        with patch.object(self.monitor, 'selected', return_value=self.stage):
            result = self.monitor.snapshot()
        self.assertEqual([row['status'] for row in result['implementation_tasks']], ['Accepted', 'Failed'])

    def test_saved_planning_results_remain_available_during_failure_review(self):
        history = [{'id': 'REVIEW-B', 'planning': True, 'planning_result': {'available': True}}]
        with patch.object(self.monitor, 'selected', return_value=self.stage), \
                patch('run_monitor_recovery.archived', return_value=history) as archived:
            result = self.monitor.snapshot()
        archived.assert_called_once()
        self.assertEqual(result['planning_tasks'], history)
        self.assertEqual(result['tasks'][0]['id'], 'FAILURE-REVIEW')

    def test_rejects_mismatched_project_plan_stage_and_outside_execution(self):
        for change in [{'project': '/elsewhere'}, {'current_run': str(self.root / 'sibling')},
                       {'current_plan': str(self.root / 'other.json')},
                       {'repairs': [{'plan': str(self.owner / 'repair-2.json')}]}, {'repairs': []}]:
            with self.subTest(change=change):
                self.save('run-1/recovery-state.json', {**self.recovery, **change})
                with patch('run_monitor.task_rows') as rows:
                    self.assertIsNone(implementation(self.stage, self.state, self.root, read, rows))
                    rows.assert_not_called()

    def test_partial_or_missing_execution_and_wrong_project_plan_hide_recovery(self):
        for path, data in [('run-1/state.json', {}), ('plan.json', {}),
                           ('plan.json', {'project': '/elsewhere', 'tasks': []})]:
            with self.subTest(path=path, data=data):
                target = self.root / path
                before = target.read_text()
                self.save(path, data)
                with patch('run_monitor.task_rows') as rows:
                    self.assertIsNone(implementation(self.stage, self.state, self.root, read, rows))
                    rows.assert_not_called()
                target.write_text(before)

    def test_execution_handoff_uses_new_queue_and_drops_recovery_preview(self):
        queue = self.save('run-1/repair-1.json', {'project': str(self.root),
            'tasks': [{'id': 'FIX', 'files': []}], 'replan_lineage': {'completed': [
                {'id': 'A', 'status': 'done', 'files': []}]}})
        self.save('run-1/repair-1/state.json', {'project': str(self.root), 'plan': str(queue),
            'status': 'running', 'current_todo': 'FIX'})
        with patch.object(self.monitor, 'selected', return_value=self.owner / 'repair-1'):
            result = self.monitor.snapshot()
        self.assertIsNone(result['implementation_state'])
        self.assertEqual(result['implementation_tasks'], [])
        self.assertEqual([row['id'] for row in result['tasks']], ['A', 'FIX'])
        self.assertEqual(result['current_todo'], 'FIX')

    def test_standalone_review_binds_queue_through_its_failure_evidence(self):
        stage=self.root/'standalone.stages'
        queue=self.save('standalone.stages/queue.json',{'tasks':[{'id':'FAILURE-REVIEW','files':[]}]})
        evidence=self.save('standalone.evidence.json',{'project':str(self.root),'plan':str(self.plan),
            'failed_todo':{'id':'B'},'local_log':str(self.owner/'02-B/pi.log')})
        state={**self.state,'plan':str(queue),'recovery_evidence':str(evidence)}
        self.save('standalone.stages/state.json',state)
        with patch.object(self.monitor,'selected',return_value=stage):
            result=self.monitor.snapshot()
        self.assertEqual([r['status'] for r in result['implementation_tasks']],['Accepted','Failed','Blocked'])
        self.assertEqual(result['implementation_state']['accepted'],1)
        packet=read(evidence)
        for change in [{'project':'/elsewhere'},{'plan':'/different.json'},
                       {'failed_todo':{'id':'C'}},{'local_log':'/outside/run/attempt/pi.log'}]:
            self.save('standalone.evidence.json',{**packet,**change})
            with patch('run_monitor.task_rows') as rows:
                self.assertIsNone(implementation(stage,state,self.root,read,rows))
                rows.assert_not_called()
