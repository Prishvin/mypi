"""Persistence, workflow routing and loopback security integration tests."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import settings
from store import Store
from server import App,handler,ThreadingHTTPServer


class Persistence(unittest.TestCase):
    def test_web_draft_requires_coverage_and_refinement_before_run_plan(self):
        from workflows import finish_plan
        from processes import Job
        from test_coverage_plan import draft
        import plans
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'data');row=store.create();job=Job(store,row['id'])
            path=Path(tmp)/'draft.json';plans.save(Path(row['project']),['.'],draft(),path)
            folder=Path(tmp)/'planning';folder.mkdir()
            store.update(row['id'],pending_plan={'folder':str(folder),'request':'Build'})
            with patch('workflows.sync_preferences'),patch('workflows.command',return_value=1):finish_plan(job,{'plan':str(path)})
            self.assertIsNone(store.get(row['id'])['plan']);self.assertIsNotNone(store.get(row['id'])['pending_plan'])
            def passed(job,argv,log):
                self.assertIn('--review-draft',argv);output=Path(argv[argv.index('--out')+1])
                data=json.loads(path.read_text());data['planning_review']={'required':True,'status':'passed'}
                plans.save(Path(row['project']),['.'],data,output);return 0
            with patch('workflows.sync_preferences'),patch('workflows.command',side_effect=passed):finish_plan(job,{'plan':str(path)})
            self.assertEqual(store.get(row['id'])['plan'],str(folder/'reviewed.json'))
            self.assertIsNone(store.get(row['id'])['pending_plan'])
    def test_planning_status_rejects_legacy_unexecutable_plan(self):
        from workflows import finish_plan
        from processes import Job
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'data');row=store.create();job=Job(store,row['id'])
            path=Path(tmp)/'plan.json';path.write_text(json.dumps({'plan_version':2,'project':row['project']}))
            with patch('workflows.sync_preferences'):
                with self.assertRaisesRegex(ValueError,'V3'):finish_plan(job,{'plan':str(path)})
            self.assertIsNone(store.get(row['id'])['plan'])

    def test_isolated_projects_and_deletion_keeps_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);a=store.create();b=store.create()
            self.assertNotEqual(a['project'],b['project'])
            source=Path(a['project'])/'user.py';source.write_text('answer=42\n')
            store.message(a['id'],'user','hello');store.update(a['id'],busy=True)
            with self.assertRaises(ValueError):store.delete(a['id'])
            restored=Store(tmp);self.assertFalse(restored.get(a['id'])['busy'])
            self.assertIn('Interrupted',restored.get(a['id'])['status'])
            self.assertEqual(restored.get(a['id'])['messages'][0]['text'],'hello')
            restored.delete(a['id']);self.assertTrue(source.exists())
            with self.assertRaises(KeyError):restored.get('../bad')
    def test_budget_rejects_impossible_and_unknown_controls(self):
        self.assertEqual(settings({'thinking_cap':8192,'output_tokens':16384})['thinking_cap'],8192)
        for values in [{'thinking_cap':9000},{'mode':'shell'},{'input_tokens':True},{'provider':'evil'}]:
            with self.assertRaises(ValueError):settings(values)


class HTTP(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App(self.tmp.name)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app,['192.168.1.34']))
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def call(self,path,method='GET',data=None,token=True,headers=None):
        h={'Content-Type':'application/json',**({'X-Local-Token':self.app.token} if token else {}),**(headers or {})}
        with urlopen(Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers=h)) as r:
            return json.load(r)
    def test_local_origin_and_action_allowlist(self):
        with self.assertRaises(HTTPError) as err:self.call('/api/conversations','POST',{},False)
        self.assertEqual(err.exception.code,403)
        with self.assertRaises(HTTPError):self.call('/api/bootstrap',headers={'Origin':'https://evil.example'})
        with self.assertRaises(HTTPError):self.call('/api/bootstrap',headers={'Host':'evil.example'})
        row=self.call('/api/conversations','POST',{})
        with patch.object(self.app.jobs,'submit') as submit:
            self.call('/api/conversations/'+row['id']+'/message','POST',{'text':'Search Wikipedia for SGF'})
            self.assertEqual(submit.call_args.args[2],'Search Wikipedia for SGF')
            with self.assertRaises(HTTPError):self.call('/api/conversations/'+row['id']+'/message','POST',{'text':'/bash rm -rf /'})
        self.call('/api/conversations/'+row['id'],'DELETE')
        self.assertTrue(Path(row['project']).exists())
    def test_conversation_monitor_is_readonly_cached_and_available_as_page(self):
        row=self.call('/api/conversations','POST',{})
        path='/api/conversations/'+row['id']+'/monitor'
        with self.assertRaises(HTTPError) as error:self.call(path)
        self.assertEqual(error.exception.code,400)
        run=Path(self.tmp.name)/'run-1';run.mkdir()
        self.app.store.update(row['id'],run_dir=str(run))
        with patch('run_monitor.RunMonitor.telemetry',return_value={'available':False}),patch.object(self.app.jobs,'submit') as submit:
            self.assertEqual(self.call(path,token=False)['total'],0)
            instance=self.app.monitors[row['id']];self.call(path)
            self.assertIs(instance,self.app.monitors[row['id']]);submit.assert_not_called()
        with urlopen(self.url+'/monitor?conversation='+row['id']) as response:
            self.assertIn(b'monitor.js',response.read())
    def test_configured_lan_host_keeps_origin_and_mutation_token_checks(self):
        lan='192.168.1.34:'+str(self.server.server_port)
        self.call('/api/bootstrap',headers={'Host':lan,'Origin':'http://'+lan})
        with self.assertRaises(HTTPError):self.call('/api/bootstrap',headers={'Host':'192.168.1.35:'+str(self.server.server_port)})
        with self.assertRaises(HTTPError):self.call('/api/conversations','POST',{},False,{'Host':lan,'Origin':'http://'+lan})
        row=self.call('/api/conversations','POST',{},True,{'Host':lan,'Origin':'http://'+lan})
        self.call('/api/conversations/'+row['id'],'DELETE',headers={'Host':lan})


if __name__=='__main__':unittest.main()
