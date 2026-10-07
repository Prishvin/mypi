"""Evidence dashboard: real gates, restart lineage, bounded private read-only telemetry."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from run_monitor import RunMonitor, read, tail_json, tools, file_status, task_status
from monitor_server import handler


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def write(self,name,data):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data));return path
    def task(self,ident='A',**values):
        return {'id':ident,'files':['code.py'],'goal':'Build','steps':['Implement','Test'],
                'acceptance':[{'id':'a','given':'Input','when':'Called','then':'Result'}],
                'tests':[['python3','-m','unittest']], 'coverage':[{'criterion':'a','test':0}],
                'depends_on':[],'context':{'max_input_tokens':8192,'max_output_tokens':4096},**values}
    def setup_run(self,tasks=None,state=None,lineage=None):
        plan=self.write('plan.json',{'project':str(self.root),'goal':'Pilot','tasks':tasks or [self.task()],
                        'replan_lineage':{'completed':lineage or []}})
        self.write('run-1/state.json',{'project':str(self.root),'plan':str(plan),'status':'running',
                   'current_todo':'A','attempt_folder':str(self.root/'run-1/01-A'),**(state or {})})
        monitor=RunMonitor(self.root,backend='http://127.0.0.1:1')
        monitor.native_at=__import__('time').monotonic();monitor.native={'available':False}
        return monitor
    def test_unavailable_partial_and_oversize_artifacts_do_not_crash(self):
        path=self.root/'partial';path.write_text('{"task":');self.assertEqual(read(path),{})
        path.write_text(' '*100);self.assertEqual(read(path,10),{})
        path.write_text('[1,2]');self.assertEqual(read(path),{})
        self.assertEqual(read(self.root/'missing'),{})
        self.assertEqual(RunMonitor(self.root,backend='http://127.0.0.1:1').snapshot()['tasks'],[])
    def test_status_distinguishes_acceptance_dependency_failure_interruption(self):
        task=self.task('B',depends_on=['A'])
        self.assertEqual(task_status(task,{},set()),'Blocked')
        self.assertEqual(task_status(task,{}, {'A'}),'Pending')
        for state,result in [('running','Running'),('needs_replan','Failed'),('interrupted','Interrupted')]:
            self.assertEqual(task_status(task,{'current_todo':'B','status':state},{'A'}),result)
        self.assertEqual(task_status(task,{'current_todo':'B','status':'needs_replan'},{'A','B'}),'Accepted')
    def test_snapshot_keeps_granular_contract_and_failure_without_invented_steps(self):
        row=self.setup_run(state={'status':'needs_replan','reason':'test_failure'}).snapshot()
        self.assertEqual(row['reason'],'test_failure');self.assertEqual(row['tasks'][0]['status'],'Failed')
        self.assertEqual(row['tasks'][0]['steps'],['Implement','Test'])
        self.assertNotIn('steps_completed',row['tasks'][0]);self.assertEqual(row['accepted'],0)
        self.assertEqual(row['tasks'][0]['context']['max_input_tokens'],8192)
    def test_replan_keeps_completed_tasks_and_follows_new_run(self):
        monitor=self.setup_run(tasks=[self.task('B')],lineage=[self.task('A',status='done')])
        row=monitor.snapshot();self.assertEqual(row['total'],2);self.assertEqual(row['accepted'],1)
        self.assertEqual(row['tasks'][0]['status'],'Accepted')
        self.write('run-2/state.json',{'status':'interrupted'})
        self.assertEqual(monitor.selected().name,'run-2')
    def test_bound_run_does_not_follow_sibling_runs(self):
        self.setup_run();monitor=RunMonitor(self.root/'run-1');self.write('run-2/state.json',{})
        self.assertEqual(monitor.selected().name,'run-1')
    def test_files_show_hash_changes_deletion_and_reject_outside_symlinks(self):
        raw=b'answer=42\n';(self.root/'code.py').write_bytes(raw)
        frozen={'before':{'files':[{'path':'code.py','sha256':hashlib.sha256(raw).hexdigest()}]}}
        self.assertEqual(file_status(self.root,['code.py'],frozen)[0]['state'],'Unchanged')
        (self.root/'code.py').write_text('answer=43\n')
        self.assertEqual(file_status(self.root,['code.py'],frozen)[0]['state'],'Changed')
        (self.root/'link').symlink_to('/etc/passwd')
        rows=file_status(self.root,['missing.py','link','../outside'],{})
        self.assertEqual([r['state'] for r in rows],['Not created','Outside project','Outside project'])
        self.assertNotIn('content',rows[1])
    def test_tool_activity_excludes_prompt_source_and_argument_dump(self):
        events=[{'type':'tool_execution_start','toolCallId':'1','toolName':'write',
                 'args':{'path':'code.py','content':'SECRET IMPLEMENTATION'}},
                {'type':'tool_execution_end','toolCallId':'1','toolName':'write','isError':True,
                 'result':{'content':[{'text':'Scope failed. Closest SOURCE: SECRET IMPLEMENTATION'}]}}]
        (self.root/'pi.log').write_text('\n'.join(map(json.dumps,events))+'\n{incomplete')
        (self.root/'tool-timing.jsonl').write_text(json.dumps({'tool_call_id':'1','wall_seconds':1.5})+'\n')
        rows=tools(self.root);self.assertEqual(rows[0]['status'],'Failed');self.assertEqual(rows[0]['seconds'],1.5)
        self.assertEqual(rows[0]['target'],'code.py');self.assertNotIn('SECRET',json.dumps(rows))
    def test_jsonl_tail_skips_partial_records(self):
        path=self.root/'events';path.write_text('garbage\n[]\n42\n'+json.dumps({'good':1})+'\n{"half":')
        self.assertEqual(tail_json(path),[{'good':1}])
    def test_snapshot_freshness_is_bound_to_final_source_and_last_results(self):
        monitor=self.setup_run();session=self.root/'session';session.mkdir()
        self.write('run-1/01-A/session.json',{'session':str(session)})
        self.write('session/task-state.json',{'evidence':{'snapshot':'old','finished_snapshot':'old',
                                              'results':[{'exit_code':0,'tests_collected':2}]}})
        with patch('tasks.current_snapshot',return_value=({}, {},'new')):
            row=monitor.snapshot()['tasks'][0]
        self.assertFalse(row['tests_fresh']);self.assertEqual(row['test_results'][0]['tests_collected'],2)
    def test_accepted_previous_attempt_keeps_tools_and_tests(self):
        monitor=self.setup_run(tasks=[self.task(status='done')],state={'current_todo':None,'attempts':[
            {'todo':'A','session':str(self.root/'session'),'log':str(self.root/'run-1/01-A/pi.log'),'gate':{'passed':True}}]})
        self.write('session/task-state.json',{'evidence':{'results':[{'exit_code':0}]}})
        log=self.root/'run-1/01-A/pi.log';log.parent.mkdir(parents=True)
        log.write_text(json.dumps({'type':'tool_execution_end','toolCallId':'1','toolName':'workflow_test','isError':False}))
        row=monitor.snapshot()['tasks'][0];self.assertEqual(row['test_results'][0]['exit_code'],0)
        self.assertEqual(row['tools'][0]['name'],'workflow_test')
        self.assertEqual(row['tools'][0]['status'],'Completed')
    def test_runner_memory_sample_supplies_rss_without_custom_observer(self):
        monitor=self.setup_run();path=self.root/'run-1/01-A/memory.jsonl';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'epoch':42,'server_rss_bytes':12345})+'\n'+json.dumps({'epoch':43,'server_rss_bytes':None})+'\n')
        row=monitor.snapshot();self.assertEqual(row['sampled_rss_bytes'],12345)
        self.assertEqual(row['rss_sample_epoch'],42)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.monitor=RunMonitor(self.root,backend='http://127.0.0.1:1')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.monitor,['192.168.0.226']))
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def get(self,path='/',**kwargs):return urlopen(Request(self.base+path,**kwargs))
    def test_dashboard_assets_status_headers_and_read_only_routes(self):
        for path in ['/','/monitor.js','/monitor-format.mjs','/monitor.css']:
            with self.get(path) as r:
                self.assertEqual(r.status,200);self.assertEqual(r.headers['Cache-Control'],'no-store')
                self.assertIn("default-src 'self'",r.headers['Content-Security-Policy'])
        with self.get('/api/status') as r:self.assertEqual(json.load(r)['total'],0)
        for path,kwargs,code in [('/api/status',{'method':'POST'},405),('/../state.json',{},404),
             ('/api/status',{'headers':{'Host':'evil.example'}},403),
             ('/api/status',{'headers':{'Origin':'https://evil.example'}},403)]:
            with self.assertRaises(HTTPError) as error:self.get(path,**kwargs)
            self.assertEqual(error.exception.code,code)
    def test_native_metrics_prefix_filter_cache_and_no_generation(self):
        requests=[]
        class Native(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                requests.append(self.path);self.send_response(200);self.end_headers()
                payload={'model_id':'quality','context_window':98304,'active_requests':2,
                         'mem':{'active_memory_bytes':123,'prompt_preview':'SECRET'},'in_flight':[
                     {'request_id':'chatcmpl-ours-1','prompt_tokens':4000,'prompt_preview':'SECRET',
                      'prefill_state':{'cached_tokens':2000,'new_prefill_tokens':2000},
                      'last_progress':{'decode_phase':'answer','completion_tokens':42,'decode_tok_s':20}},
                     {'request_id':'chatcmpl-other-1','prompt_preview':'OTHER SECRET'}]}
                self.wfile.write(b'data: '+json.dumps(payload).encode()+b'\n\n')
        native=ThreadingHTTPServer(('127.0.0.1',0),Native)
        threading.Thread(target=native.serve_forever,daemon=True).start()
        try:
            self.monitor.backend='http://127.0.0.1:'+str(native.server_port)+'/v1'
            row=self.monitor.telemetry(['chatcmpl-ours-']);self.monitor.telemetry(['chatcmpl-ours-'])
            self.assertEqual(requests,['/v1/mtplx/metrics/stream'])
            self.assertEqual(row['other_requests'],1);self.assertEqual(row['requests'][0]['output_tokens'],42)
            self.assertEqual(row['requests'][0]['cached_tokens'],2000)
            self.assertNotIn('SECRET',json.dumps(row));self.assertNotIn('other-1',json.dumps(row))
        finally:native.shutdown();native.server_close()
