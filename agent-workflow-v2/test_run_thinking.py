"""Monitor real Pi reasoning events without mixing requests, arguments or answers."""
import json
from pathlib import Path
import tempfile
import unittest
from run_thinking import ThinkingFeed


def update(kind, **values):
    return {'type':'message_update','assistantMessageEvent':{'type':kind,**values}}


class ThinkingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'pi.log';self.feed=ThinkingFeed()

    def append(self,*events):
        with self.path.open('a') as output:
            for event in events:output.write(json.dumps(event)+'\n')

    def test_live_deltas_are_incremental_and_end_snapshot_does_not_duplicate(self):
        self.append(update('thinking_start'),update('thinking_delta',delta='Check '))
        self.assertEqual(self.feed.snapshot(self.path,True)['text'],'Check ')
        self.assertEqual(self.feed.snapshot(self.path,True)['text'],'Check ')
        self.append(update('thinking_delta',delta='the boundary.'),update('thinking_end',content='Check the boundary.'))
        row=self.feed.snapshot(self.path,True)
        self.assertEqual(row['text'],'Check the boundary.');self.assertFalse(row['streaming'])
        self.append({'type':'message_end','message':{'role':'assistant','content':[
            {'type':'thinking','thinking':'Check the boundary.','thinkingSignature':'PRIVATE SIGNATURE'},
            {'type':'toolCall','arguments':{'content':'PRIVATE CODE'}}]}})
        self.assertEqual(self.feed.snapshot(self.path,True)['text'],'Check the boundary.')

    def test_only_explicit_assistant_thinking_is_exposed(self):
        self.append({'type':'message_end','message':{'role':'user','content':[{'type':'thinking','thinking':'PRIVATE PROMPT'}]}},
                    update('text_delta',delta='PRIVATE ANSWER'),update('toolcall_delta',delta='PRIVATE ARGUMENTS'),
                    {'type':'tool_execution_end','result':{'content':[{'text':'PRIVATE RESULT'}]}},
                    update('thinking_delta',delta='<img src=x onerror=alert(1)>'))
        row=self.feed.snapshot(self.path,True)
        self.assertEqual(row['text'],'<img src=x onerror=alert(1)>')
        self.assertNotIn('PRIVATE',json.dumps(row))

    def test_request_transition_labels_previous_text_and_new_reasoning_replaces_it(self):
        self.append(update('thinking_delta',delta='First'),update('toolcall_start'))
        self.assertFalse(self.feed.snapshot(self.path,True)['streaming'])
        self.append({'type':'message_start','message':{'role':'assistant'}})
        row=self.feed.snapshot(self.path,True);self.assertEqual(row['text'],'First');self.assertTrue(row['previous'])
        self.append(update('thinking_start'),update('thinking_delta',delta='Second'))
        row=self.feed.snapshot(self.path,True);self.assertEqual(row['text'],'Second');self.assertTrue(row['streaming'])
        self.assertFalse(self.feed.snapshot(self.path,False)['streaming'])

    def test_partial_utf8_and_json_wait_for_complete_record(self):
        raw=(json.dumps(update('thinking_delta',delta='évidence'),ensure_ascii=False)+'\n').encode()
        split=raw.index('é'.encode())+1
        self.path.write_bytes(raw[:split]);self.assertEqual(self.feed.snapshot(self.path,True)['text'],'')
        with self.path.open('ab') as out:out.write(raw[split:])
        self.assertEqual(self.feed.snapshot(self.path,True)['text'],'évidence')

    def test_tail_bootstrap_and_text_limits_are_explicit(self):
        self.feed=ThinkingFeed(read_limit=500,text_limit=20)
        self.path.write_text('x'*1000+'\n');self.append(update('thinking_delta',delta='a'*30))
        row=self.feed.snapshot(self.path,True);self.assertEqual(row['text'],'a'*20);self.assertTrue(row['truncated'])
        self.assertLessEqual(len(self.feed.pending),500)

    def test_attempt_switch_rotation_and_missing_log_never_reuse_previous_attempt(self):
        self.append(update('thinking_delta',delta='Old attempt'));self.feed.snapshot(self.path,True)
        other=self.path.with_name('next.log');other.touch()
        self.assertEqual(self.feed.snapshot(other,True)['text'],'')
        self.feed.snapshot(self.path,True);self.path.write_text('{}\n')
        self.assertEqual(self.feed.snapshot(self.path,True)['text'],'')
        self.path.unlink();self.assertEqual(self.feed.snapshot(self.path,True)['text'],'')

    def test_malformed_and_oversized_records_recover_at_next_complete_line(self):
        self.feed=ThinkingFeed(read_limit=300);self.path.write_text('x'*400)
        self.feed.snapshot(self.path,True)
        with self.path.open('a') as out:out.write('y'*400+'\n[]\n{"broken":\n')
        self.append(update('thinking_delta',delta='Recovered'))
        self.assertEqual(self.feed.snapshot(self.path,True)['text'],'Recovered')
