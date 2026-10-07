"""A generated correction cannot execute before exact-digest approval and preservation checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import plans
import tasks
from contract_revision import prepare, inspect, approve, propose
from plan_draft import apply, digest
from project_map import scan
from test_coverage_plan import draft


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.root = self.base/'project'; self.root.mkdir()
        self.parent = self.base/'parent.json'; plans.save(self.root, ['.'], draft(), self.parent)
        self.original = json.loads(self.parent.read_text())
        self.session = self.base/'failed-session'; self.session.mkdir()
        tasks.begin(self.root, ['.'], self.original['tasks'][0], self.session/'task-state.json')
        self.packet = {'project': str(self.root), 'plan': str(self.parent), 'goal': self.original['goal'],
            'failed_todo': self.original['tasks'][0], 'remaining': self.original['tasks'],
            'completed': [{'id': 'T0', 'goal': 'Previously accepted', 'files': ['prior.mjs'], 'evidence': '/prior/evidence'}],
            'current_snapshot': scan(self.root, ['.'])['snapshot'], 'acceptance_fixtures': {},
            'reason': 'contract_conflict', 'failed_tests': [], 'session': str(self.session)}
        self.evidence = self.base/'evidence.json'; self.evidence.write_text(json.dumps(self.packet))
        self.folder = self.base/'revision'; self.proposal = self.folder/'proposal.json'
        self.output = self.base/'approved.json'
        self.reason = 'Review a contradictory generated criterion without changing user intent.'

    def candidate(self):
        _, _, data = prepare(self.root, self.evidence, self.folder, self.reason)
        old = copy.deepcopy(data['tasks'][0]['acceptance'][0])
        self.correction = {'old': old, 'new': {**old, 'then': 'Return the documented normalized value'},
                           'reason': 'The generated expectation contradicts its documented interface.'}
        result = apply(data, {'task_updates': [{'id': data['tasks'][0]['id'],
                                               'criterion_replacements': [self.correction]}]})
        plans.save(self.root, ['.'], result, self.proposal)
        return json.loads(self.proposal.read_text())

    def test_proposal_is_non_executable_and_does_not_change_source_or_parent(self):
        before = scan(self.root, ['.'])['snapshot']; parent = self.parent.read_bytes()
        data = self.candidate()
        with self.assertRaisesRegex(ValueError, 'explicit approval'): plans.require_review(data)
        with self.assertRaisesRegex(ValueError, 'explicit approval'): plans.select(self.proposal, data['tasks'][0]['id'])
        self.assertEqual(inspect(self.root, self.proposal)[3][0]['old'], self.correction['old'])
        self.assertEqual(self.parent.read_bytes(), parent)
        self.assertEqual(scan(self.root, ['.'])['snapshot'], before)

    def test_exact_approval_retains_lineage_baseline_and_both_criterion_versions(self):
        proposal = self.candidate(); before = copy.deepcopy(proposal)
        result = approve(self.root, self.proposal, self.output, digest(proposal), 'Explicit user approval of the shown exact correction.')
        self.assertFalse(result['execution_started'])
        saved = json.loads(self.output.read_text()); plans.require_review(saved)
        self.assertEqual(saved['replan_lineage']['completed'], self.packet['completed'])
        self.assertEqual(saved['tasks'][0]['baseline'], str(self.session/'task-state.json'))
        self.assertEqual(saved['tasks'][1], proposal['tasks'][1])
        for key in ('goal', 'files', 'tests', 'coverage', 'depends_on'):
            self.assertEqual(saved['tasks'][0][key], proposal['tasks'][0][key])
        receipt = saved['contract_revision']
        self.assertEqual(receipt['status'], 'approved')
        self.assertEqual(receipt['corrections'][0]['old'], self.correction['old'])
        self.assertEqual(receipt['corrections'][0]['new'], self.correction['new'])
        self.assertEqual(json.loads(self.proposal.read_text()), before)
        self.assertEqual(json.loads(self.evidence.read_text()), self.packet)

    def test_wrong_digest_or_short_approval_cannot_publish(self):
        data = self.candidate()
        for sha, reason in [('wrong', self.reason), (digest(data), 'ok')]:
            with self.assertRaises(ValueError): approve(self.root, self.proposal, self.output, sha, reason)
        self.assertFalse(self.output.exists())

    def test_criteria_only_approval_does_not_adopt_other_model_strategy_changes(self):
        data = self.candidate()
        original = copy.deepcopy(data['tasks'][0])
        data['tasks'][0]['steps'] = ['Different proposed strategy', 'Different proposed validation']
        data['tasks'][0]['test_strategy'] = 'Different proposed test strategy that the user did not approve.'
        self.proposal.write_text(json.dumps(data))
        approve(self.root, self.proposal, self.output, digest(data), self.reason, criteria_only=True)
        approved = json.loads(self.output.read_text()); selected = approved['tasks'][0]
        for key in ('steps', 'assumptions', 'test_strategy', 'context', 'execution', 'acceptance'):
            self.assertEqual(selected[key], original[key])
        self.assertEqual(approved['contract_revision']['selection'], 'criteria_only')
        self.assertEqual(approved['contract_revision']['excluded_proposal_fields'], ['steps','test_strategy'])
        self.assertEqual(json.loads(self.proposal.read_text()), data)

    def test_edited_source_parent_or_evidence_rejects_approval(self):
        data = self.candidate(); sha = digest(data)
        (self.root/'changed.py').write_text('x=1')
        with self.assertRaisesRegex(ValueError, 'stale'): approve(self.root, self.proposal, self.output, sha, self.reason)
        (self.root/'changed.py').unlink()
        old = self.parent.read_bytes(); self.parent.write_text(json.dumps({**self.original, 'goal': 'Different intent'}))
        with self.assertRaisesRegex(ValueError, 'binding changed'): approve(self.root, self.proposal, self.output, sha, self.reason)
        self.parent.write_bytes(old)
        self.evidence.write_text(json.dumps({**self.packet, 'reason': 'different'}))
        with self.assertRaisesRegex(ValueError, 'binding changed'): approve(self.root, self.proposal, self.output, sha, self.reason)

    def test_protected_fields_and_unrelated_tasks_cannot_change(self):
        original = self.candidate()
        changes = [lambda p:p.update(goal='Different'), lambda p:p.update(architecture='Other'),
            lambda p:p['tasks'][0].update(files=['else.py']), lambda p:p['tasks'][0].update(tests=[['echo','pass']]),
            lambda p:p['tasks'][0].update(coverage=[]), lambda p:p['tasks'][0].update(goal='Other'),
            lambda p:p['tasks'][1].update(steps=['Different']), lambda p:p['tasks'].pop()]
        for change in changes:
            data = copy.deepcopy(original); change(data); self.proposal.write_text(json.dumps(data))
            with self.subTest(change=change), self.assertRaises(ValueError): inspect(self.root, self.proposal)

    def test_unrecorded_deleted_duplicate_and_wrong_target_corrections_are_rejected(self):
        original = self.candidate()
        changes = [lambda p:p['draft_repair'].update(criterion_corrections=[]),
            lambda p:p['tasks'][0]['acceptance'][0].update(then='Unrecorded'),
            lambda p:p['tasks'][0]['acceptance'].pop(),
            lambda p:p['draft_repair']['criterion_corrections'][0].update(todo='T2'),
            lambda p:p['draft_repair']['criterion_corrections'].append(p['draft_repair']['criterion_corrections'][0])]
        for change in changes:
            data = copy.deepcopy(original); change(data); self.proposal.write_text(json.dumps(data))
            with self.subTest(change=change), self.assertRaises(ValueError): inspect(self.root, self.proposal)

    def test_changed_pinned_draft_is_rejected(self):
        self.candidate(); path = self.folder/'draft.json'; data = json.loads(path.read_text())
        data['tasks'][1]['goal'] = 'Changed'; path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Pinned revision draft changed'): inspect(self.root, self.proposal)

    def test_accepted_external_fixture_is_checked_even_when_not_in_pending_commands(self):
        fixture = self.base/'accepted-check.mjs'; fixture.write_text('export const expected = 1;')
        self.original['acceptance_fixtures'] = {str(fixture): tasks.hash_file(fixture)}
        self.parent.write_text(json.dumps(self.original))
        self.packet['acceptance_fixtures'] = self.original['acceptance_fixtures']
        self.evidence.write_text(json.dumps(self.packet))
        data = self.candidate()
        fixture.write_text('export const expected = 2;')
        with self.assertRaisesRegex(ValueError, 'immutable fixture changed'):
            approve(self.root, self.proposal, self.output, digest(data), self.reason)
        self.assertFalse(self.output.exists())

    def test_completed_target_wrong_project_existing_or_internal_output_rejected(self):
        for change in ({'completed': [{'id': 'T1'}]}, {'project': str(self.base/'other')}):
            self.evidence.write_text(json.dumps({**self.packet, **change}))
            with self.assertRaises(ValueError): prepare(self.root, self.evidence, self.folder, self.reason)
        self.evidence.write_text(json.dumps(self.packet))
        with self.assertRaises(ValueError): prepare(self.root, self.evidence, self.root/'revision', self.reason)
        self.candidate()
        with self.assertRaises(ValueError): prepare(self.root, self.evidence, self.folder, self.reason)

    def test_native_proposal_orchestration_never_approves_or_executes(self):
        def fake(root, source, output, planner, timeout, prompt, mode, target, **kwargs):
            self.assertEqual(mode, ['--refine-task', 'T1']); self.assertEqual(kwargs['phase'], 'recovery')
            self.assertIn('Changing a test', prompt)
            data = json.loads(source.read_text()); old = data['tasks'][0]['acceptance'][0]
            patch_data = {'task_updates': [{'id': target, 'criterion_replacements': [
                {'old':old, 'new':{**old,'then':'Return the documented result'}, 'reason':self.reason}]}]}
            plans.save(root, ['.'], apply(data, patch_data), output)
            return {'passed':True,'exit_code':0}
        with patch('plan_refinement.invoke_review', side_effect=fake):
            result = propose(self.root, self.evidence, self.folder, self.reason)
        self.assertTrue(result['requires_approval'])
        self.assertEqual(result['proposal_sha256'], digest(json.loads(self.proposal.read_text())))
        with self.assertRaises(ValueError): plans.require_review(json.loads(self.proposal.read_text()))


if __name__ == '__main__': unittest.main()
