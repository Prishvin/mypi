"""RPC framing and the actual prepared role restrictions."""
import json
import queue
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rpc import records
from config import DEFAULTS
from store import Store
import pi_session


class RPC(unittest.TestCase):
    def test_framing_preserves_unicode_and_ignores_bad_lines(self):
        output=queue.Queue();records(BytesIO('noise\n{"text":"x\u2028y"}\r\n'.encode()),output)
        self.assertEqual(output.get(),{'text':'x\u2028y'});self.assertIsNone(output.get())
    def test_chat_preparation_has_no_edit_or_shell_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            row=Store(Path(tmp)/'data').create()
            prepared=pi_session.prepare(row,Path(tmp)/'chat')
            tools=prepared['command'][prepared['command'].index('--tools')+1].split(',')
            self.assertEqual(set(tools),{'project_map','skill_use','skill_read'})
            self.assertEqual(prepared['context'],98304);self.assertEqual(prepared['input_budget'],24576)
            self.assertTrue(prepared['interactive']);self.assertFalse(prepared['cloud'])
            self.assertIn('rpc',prepared['command']);self.assertTrue((Path(prepared['runtime'])/'chat-rules.txt').exists())


class Stats(unittest.TestCase):
    def test_metrics_preserve_phase_wall_and_native_rss_distinction(self):
        from stats import aggregate
        result=aggregate([{'wall_seconds':7,'metrics':{'requests':2,'input_tokens_sum':10,'output_tokens_sum':8,'server_rss_peak_sampled_bytes':100,'native_requests':[{'active_memory_bytes':90}]}},
                          {'wall_seconds':3,'metrics':{'requests':1,'input_tokens_sum':20,'server_rss_peak_sampled_bytes':80}}])
        self.assertEqual(result['wall_seconds'],10);self.assertEqual(result['requests'],3)
        self.assertEqual(result['input_tokens_sum'],30);self.assertEqual(result['server_rss_peak_sampled_bytes'],100)
        self.assertEqual(result['native_requests'][0]['active_memory_bytes'],90)


if __name__=='__main__':unittest.main()
