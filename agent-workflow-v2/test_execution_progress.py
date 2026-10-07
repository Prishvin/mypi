"""Prove early stagnation detection without mistaking identical activity for progress."""
import json
from pathlib import Path
import tempfile
import unittest
from execution_progress import advance
from progress_observer import check, clean


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {'files': {'source.py': 'one'}, 'tests': []}
        self.state = advance({}, self.evidence, [])

    def round(self, extras=()):
        self.state = advance(self.state, self.evidence, [{'kind': 'round'}, *extras])
        return self.state['brief']

    def test_idle_rounds_warn_at_two_stop_at_four(self):
        for i in range(1, 5):
            brief = self.round()
            self.assertEqual(brief['status'], 'continue' if i < 2 else 'warning' if i < 4 else 'stop')

    def test_distinct_successful_reads_get_bounded_grace_without_resetting_rounds(self):
        for i in range(1, 9):
            brief = self.round([{'kind': 'tool', 'tool': 'source_query', 'selector': {'offset': i}}])
            self.assertEqual(brief['rounds_without_progress'], i)
            self.assertEqual(brief['retrieval_grace_rounds'], min(i, 4))
            self.assertEqual(brief['status'], 'continue' if i < 2 else 'warning' if i < 8 else 'stop')

    def test_errors_or_empty_selectors_do_not_grant_retrieval_grace(self):
        for i in range(1, 5):
            brief = self.round([{'kind': 'tool', 'tool': 'source_query', 'selector': {'offset': i}, 'error': 'no such file'},
                                {'kind': 'tool', 'tool': 'project_map', 'selector': {}}])
        self.assertEqual(brief['status'], 'stop')
        self.assertEqual(brief['retrieval_grace_rounds'], 0)

    def test_content_change_resets_grace_but_does_not_remove_bounds(self):
        self.round([{'kind': 'tool', 'tool': 'source_query', 'selector': {'path': 'source.py'}}])
        self.evidence['files']['source.py'] = 'two'
        brief = self.round()
        self.assertEqual(brief['retrieval_grace_rounds'], 0)
        self.assertEqual(brief['no_progress_round_limit'], 4)

    def test_repeated_compactions_stop_after_three_completed_unchanged_rounds(self):
        for _ in range(2):
            self.assertNotEqual(self.round([{'kind': 'compaction'}])['status'], 'stop')
        self.assertEqual(self.round([{'kind': 'compaction'}])['status'], 'stop')

    def test_compactions_alone_do_not_consume_model_rounds(self):
        self.state = advance(self.state, self.evidence, [{'kind': 'compaction'}] * 6)
        self.assertEqual(self.state['brief']['status'], 'continue')

    def test_three_repeated_reads_stop_but_new_pages_have_grace(self):
        event = {'kind': 'tool', 'tool': 'source_query', 'selector': {'path': 'source.py'}}
        self.round([event]); self.round([event])
        self.assertEqual(self.round([event])['status'], 'stop')

    def test_real_edit_resets_window_but_identical_write_or_revert_does_not(self):
        self.round(); self.round()
        self.evidence['files']['source.py'] = 'two'
        self.assertEqual(self.round()['rounds_without_progress'], 0)
        self.assertEqual(self.round()['rounds_without_progress'], 1)
        self.evidence['files']['source.py'] = 'one'
        self.assertEqual(self.round()['rounds_without_progress'], 2)

    def test_new_test_outcome_resets_window_and_same_result_does_not(self):
        self.round(); self.round(); self.round()
        self.evidence['tests'] = [{'exit_code': 1, 'observations': ['failing boundary']}]
        self.assertEqual(self.round()['rounds_without_progress'], 0)
        self.assertEqual(self.round()['rounds_without_progress'], 1)
        self.evidence['tests'][0]['exit_code'] = 0
        self.assertEqual(self.round()['rounds_without_progress'], 0)

    def test_history_keeps_errors_across_changes_without_mutating_prior_state(self):
        before = json.dumps(self.state)
        events = [{'kind': 'tool', 'tool': 'edit', 'selector': {'path': 'source.py'}, 'error': 'exact text mismatch'}] * 20
        result = advance(self.state, self.evidence, events)
        self.assertEqual(json.dumps(self.state), before)
        self.assertEqual(len(result['recent']), 8); self.assertEqual(len(result['errors']), 3)
        result = advance(result, {'files': {'source.py': 'two'}}, [])
        self.assertEqual(result['brief']['recent_errors'][-1]['error'], 'exact text mismatch')


class ObserverTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name); self.root = self.base/'project'; self.root.mkdir()
        self.session = self.base/'session'; self.session.mkdir()
        (self.root/'one.py').write_text('PRIVATE_IMPLEMENTATION')
        self.contract = {'before': {'root': str(self.root)}, 'task': {'id': 'T1', 'files': ['one.py']}}
        self.save_contract()

    def save_contract(self):
        (self.session/'task-state.json').write_text(json.dumps(self.contract))

    def event(self, row):
        with (self.session/'execution-events.jsonl').open('a') as out:
            out.write(json.dumps(row)+'\n')

    def test_cursor_persists_and_repeated_checks_do_not_increase_counters(self):
        check(self.session)
        self.event({'kind': 'round'})
        self.assertEqual(check(self.session)['rounds_without_progress'], 1)
        self.assertEqual(check(self.session)['rounds_without_progress'], 1)
        self.assertNotIn('PRIVATE_IMPLEMENTATION', (self.session/'execution-progress.json').read_text())

    def test_incomplete_tail_is_consumed_only_when_finished(self):
        check(self.session)
        journal=self.session/'execution-events.jsonl';journal.write_bytes(b'{"kind":"round"')
        self.assertEqual(check(self.session)['rounds_without_progress'], 0)
        with journal.open('ab') as out:out.write(b'}\n')
        self.assertEqual(check(self.session)['rounds_without_progress'], 1)

    def test_timing_only_changes_in_test_log_do_not_reset_progress(self):
        log=self.session/'test.log';log.write_text('✖ boundary (10ms)\nℹ duration_ms 10')
        self.contract['evidence']={'results':[{'argv':['test'], 'exit_code':1,'tests_collected':2,'log':str(log)}]}
        self.save_contract();check(self.session)
        self.event({'kind':'round'});check(self.session)
        log.write_text('✖ boundary (80ms)\nℹ duration_ms 80')
        self.event({'kind':'round'})
        self.assertEqual(check(self.session)['rounds_without_progress'],2)
        self.contract['evidence']['results'][0]['exit_code']=0;self.save_contract()
        self.assertEqual(check(self.session)['rounds_without_progress'],0)

    def test_stop_is_durable_and_bound_to_project_and_task(self):
        check(self.session)
        for _ in range(5):self.event({'kind':'round'})
        self.assertEqual(check(self.session)['status'],'stop')
        marker=json.loads((self.session/'progress-stop.json').read_text())
        self.assertEqual(marker['identity'],{'project':str(self.root.resolve()),'task':'T1'})
        (self.root/'one.py').write_text('changed after stop')
        self.assertEqual(check(self.session)['status'],'stop')
        self.contract['task']['id']='T2';self.save_contract()
        with self.assertRaisesRegex(ValueError,'another task'):check(self.session)

    def test_outside_source_or_test_logs_are_never_read(self):
        outside=self.base/'outside';outside.write_text('PRIVATE_OUTSIDE')
        self.contract['evidence']={'results':[{'argv':['test'], 'exit_code':1, 'log':str(outside)}]}
        self.save_contract();self.assertEqual(check(self.session)['tests'][0]['observations'],[])
        (self.root/'escape').symlink_to(outside)
        self.contract['task']['files']=['escape'];self.save_contract()
        with self.assertRaisesRegex(ValueError,'escapes'):check(self.session)

    def test_journal_corruption_is_visible_and_does_not_reset_counters(self):
        check(self.session);self.event({'kind':'round'});check(self.session)
        (self.session/'execution-events.jsonl').write_text('')
        with self.assertRaisesRegex(ValueError,'truncated'):check(self.session)

    def test_event_metadata_is_bounded_and_bodies_are_discarded(self):
        row=clean({'kind':'tool','tool':'edit','selector':{'path':'one.py','content':'PRIVATE_SOURCE'},
                   'error':'Traceback (most recent call last):\n    PRIVATE_SOURCE\nValueError: exact text mismatch\nReceived arguments: PRIVATE_SOURCE'})
        self.assertNotIn('PRIVATE_SOURCE',json.dumps(row))
        self.assertEqual(row['error'],'ValueError: exact text mismatch')
        self.assertLess(len(json.dumps(clean({'kind':'tool','selector':{'query':'x'*10000}}))),300)


if __name__ == '__main__':unittest.main()
