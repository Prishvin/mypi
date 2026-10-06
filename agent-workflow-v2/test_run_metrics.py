"""Verify backend evidence attribution across fresh Pi/OpenCode sessions."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from run_metrics import collect,transport_for_session

class MetricsTests(unittest.TestCase):
    def test_cancelled_native_generation_is_counted_separately_from_provider_usage(self):
        """An interrupted buffered tool payload must not disappear from performance evidence."""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);session=root/'unique-session';session.mkdir()
            folder=root/'attempt';folder.mkdir()
            (session/'provider-timing.jsonl').write_text(json.dumps({'type':'request_end',
                'usage':{'input':100,'output':20,'reasoning':5}})+'\n')
            native=[{'request_id':'unique-session-1','completion_tokens':20},
                    {'request_id':'unique-session-2','completion_tokens':500,
                     'request_cancelled':True,'cancellation_reason':'client_disconnect'}]
            with patch('run_metrics.BASE',root/'flow'),patch('remote_metrics.native_for',return_value=native):
                result=collect({'session':str(session)},folder)
            self.assertEqual(result['requests'],1)
            self.assertEqual(result['output_tokens_sum'],20)
            self.assertEqual(result['native_request_count'],2)
            self.assertEqual(result['native_completion_tokens_sum'],520)
            self.assertEqual(result['native_cancelled_requests'],1)
            self.assertTrue(result['native_requests'][1]['request_cancelled'])
            self.assertEqual(result['native_requests'][1]['cancellation_reason'],'client_disconnect')
            self.assertFalse(result['server_rss_available'])
            (folder/'memory.jsonl').write_text(json.dumps({'server_rss_bytes':1234})+'\n')
            with patch('run_metrics.BASE',root/'flow'),patch('remote_metrics.native_for',return_value=native):
                result=collect({'session':str(session)},folder)
            self.assertTrue(result['server_rss_available'])
            self.assertEqual(result['server_rss_peak_sampled_bytes'],1234)

    def test_generic_early_session_uses_only_its_attempt_time_range(self):
        events=[{'timestamp':10000},{'timestamp':20000}]
        transport=[{'request_id':'session-10000','phase':'usage'},
                   {'request_id':'session-1000','phase':'usage'},
                   {'request_id':'session-30000','phase':'finished'},
                   {'request_id':'oc-other-10000','phase':'usage'}]
        self.assertEqual(transport_for_session(events,transport,'session'),[transport[0]])

    def test_opencode_usage_is_attributed_to_only_its_unique_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);flow=root/'flow';flow.mkdir();folder=root/'attempt';folder.mkdir()
            session=folder/'oc-123';session.mkdir();logs=root/'native';logs.mkdir()
            reports=root/'reports';reports.mkdir()
            (reports/'quality-main-status.json').write_text(json.dumps({'logs':str(logs)}))
            (logs/'requests.jsonl').write_text('\n'.join(json.dumps(r) for r in [
                {'request_id':'oc-123-1','completion_tokens':20,'decode_tok_s':10},
                {'request_id':'oc-other-2','completion_tokens':999}]))
            (folder/'pi.log').write_text(json.dumps({'type':'step_finish','part':{'tokens':
                {'input':100,'output':20,'reasoning':5,'cache':{'read':50}}}})+'\n')
            gateway=reports/'overnight-quake-20261006/gateway';gateway.mkdir(parents=True)
            (gateway/'events.jsonl').write_text('\n'.join(json.dumps(r) for r in [
                {'request_id':'oc-123-1','phase':'finished','seconds':2},
                {'request_id':'oc-other-2','phase':'finished','seconds':100}]))
            with patch('run_metrics.BASE',flow):data=collect({'session':str(session)},folder)
            self.assertEqual((data['requests'],data['input_tokens_sum'],data['output_tokens_sum']), (1,100,25))
            self.assertEqual(data['visible_output_tokens_sum'],20)
            self.assertEqual(data['reasoning_tokens_sum'],5);self.assertEqual(data['cache_read_tokens_sum'],50)
            self.assertEqual(data['request_seconds'],2);self.assertEqual(len(data['native_requests']),1)
            self.assertEqual(data['native_requests'][0]['completion_tokens'],20)
            with (gateway/'events.jsonl').open('a') as out:
                out.write('\n'+json.dumps({'request_id':'oc-123-1','phase':'usage','usage':{
                    'prompt_tokens':150,'prompt_tokens_details':{'cached_tokens':50},
                    'completion_tokens':25,'completion_tokens_details':{'reasoning_tokens':5}}}))
            # The last tool-producing step may abort before SDK step_finish is printed.
            (folder/'pi.log').write_text('')
            with patch('run_metrics.BASE',flow):data=collect({'session':str(session)},folder)
            self.assertEqual((data['requests'],data['input_tokens_sum'],data['output_tokens_sum']), (1,100,25))
            self.assertIn('final tool-producing',data['usage_source'])

if __name__=='__main__':unittest.main()
