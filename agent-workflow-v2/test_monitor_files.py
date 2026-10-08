"""File previews expose declared source as bounded text, never arbitrary paths."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from urllib.parse import urlencode
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from monitor_files import preview, MAX_BYTES
from monitor_server import handler


class FilePreview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'project';self.root.mkdir()
        self.run=self.base/'run-1';self.run.mkdir()
        (self.run/'state.json').write_text(json.dumps({'project':str(self.root)}))
        self.name='test/code #1.js';path=self.root/self.name;path.parent.mkdir();path.write_text('<script>alert(1)</script>\n')
        self.monitor=Mock();self.monitor.selected.return_value=self.run
        self.monitor.snapshot.return_value={'run':'run-1','tasks':[{'files':[{'path':self.name}]}]}

    def read(self,name=None,run='run-1'):
        return preview(self.monitor,urlencode({'run':run,'path':name or self.name}))

    def test_declared_file_is_exact_plain_text_and_does_not_generate(self):
        result=self.read();self.assertEqual(result['content'],'<script>alert(1)</script>\n')
        self.assertTrue(result['readonly']);self.assertFalse(result['truncated'])
        self.monitor.telemetry.assert_not_called()

    def test_paused_implementation_file_is_available_during_review(self):
        data=self.monitor.snapshot.return_value;data['implementation_tasks']=data.pop('tasks')
        self.assertIn('content',self.read())

    def test_undeclared_absolute_and_parent_paths_rejected_even_if_listed(self):
        for name in ['secret.txt','../outside','/etc/passwd']:
            if name!='secret.txt':self.monitor.snapshot.return_value['tasks'][0]['files'].append({'path':name})
            with self.subTest(name=name),self.assertRaises(PermissionError):self.read(name)

    def test_file_and_directory_symlinks_rejected(self):
        target=self.base/'outside';target.write_text('private')
        path=self.root/self.name;path.unlink();path.symlink_to(target)
        with self.assertRaises(PermissionError):self.read()
        path.unlink();path.parent.rmdir();path.parent.symlink_to(self.base)
        with self.assertRaises(PermissionError):self.read()

    def test_missing_binary_and_large_files(self):
        path=self.root/self.name;path.unlink()
        with self.assertRaises(FileNotFoundError):self.read()
        path.write_bytes(b'\0binary')
        with self.assertRaisesRegex(ValueError,'binary'):self.read()
        path.write_text('x'*(MAX_BYTES+100));result=self.read()
        self.assertEqual(len(result['content']),MAX_BYTES);self.assertTrue(result['truncated'])

    def test_stale_or_duplicate_binding_rejected(self):
        with self.assertRaisesRegex(ValueError,'run changed'):self.read(run='run-0')
        for query in ['path=x','run=run-1&path=x&path=y','run=run-1&path=x&root=/']:
            with self.subTest(query=query),self.assertRaises(ValueError):preview(self.monitor,query)

    def test_real_http_file_route_and_assets(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.monitor))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            with urlopen(base+'/api/file?'+urlencode({'run':'run-1','path':self.name})) as response:
                self.assertEqual(response.headers.get_content_type(),'application/json')
                self.assertIn('<script>',json.load(response)['content'])
            for asset in ['file.html','file-viewer.mjs']:
                with urlopen(base+'/'+asset) as response:self.assertEqual(response.status,200)
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
