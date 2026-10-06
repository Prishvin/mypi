"""Prove change-type handling, missing-map bootstrap and zero-model native maintenance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from architecture_maintenance import changes, maintain
from project_map import scan
from tasks import begin
from skill_runner import prepare, run


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name).resolve();self.root=base/'project';self.root.mkdir()
        self.session=base/'session';self.session.mkdir();self.state=self.session/'state.json'
        self.source=self.root/'logic.py';self.source.write_text('def step(x):\n    """Advance a step."""\n    return x+1\n')
        (self.root/'architecture.md').write_text('# Rules\nlogic.py owns deterministic rules.\n')
        self.contract=begin(self.root,['.'],{'goal':'Change rules','files':['logic.py','new.py'],'acceptance':['Works'],
            'tests':[[sys.executable,'-c','assert True']]},self.state)
        self.out=Path(self.contract['shadow'])
        (self.session/'launch.json').write_text(json.dumps({'role':'code','project':str(self.root),'state':str(self.state),
            'shadow':str(self.out),'prefixes':['.']}))

    def test_body_only_change_updates_architecture_hash_and_map_without_model(self):
        self.source.write_text(self.source.read_text().replace('x+1','x+2'))
        result=maintain(self.root,['.'],self.out,self.state)
        self.assertEqual(result['changes'],[{'path':'logic.py','type':'modified','interface_changed':False}])
        self.assertTrue(result['architecture_updated']);self.assertTrue(result['map_rebuilt']);self.assertTrue(result['in_sync'])
        self.assertEqual(result['implementation'],'Python; no model request')

    def test_interface_change_new_file_deletion_and_same_content_rename(self):
        before=scan(self.root,['.'])
        self.source.write_text('def advance(x):\n    """Advance a step."""\n    return x+1\n')
        row=changes(before,scan(self.root,['.']))[0]
        self.assertTrue(row['interface_changed'])
        self.source.write_text('def step(x):\n    """Advance a step."""\n    return x+1\n')
        self.source.rename(self.root/'new.py')
        result=maintain(self.root,['.'],self.out,self.state)
        self.assertEqual(result['changes'][0]['type'],'renamed');self.assertEqual(result['changes'][0]['from_path'],'logic.py')
        text=(self.root/'architecture.md').read_text();self.assertIn('"deleted": true',text);self.assertIn('new.py',text)
        before=scan(self.root,['.']);(self.root/'new.py').unlink()
        self.assertEqual(changes(before,scan(self.root,['.']))[0]['type'],'deleted')
        (self.root/'new.py').write_text('def create():\n    """Create a value."""\n    return 1\n')
        self.assertEqual(changes(scan_empty(before),scan(self.root,['.']))[0]['type'],'added')

    def test_missing_map_is_created_and_fresh_map_is_not_rewritten(self):
        path=self.out/'architecture-map.md';path.unlink()
        result=maintain(self.root,['.'],self.out,self.state)
        self.assertTrue(result['map_rebuilt']);self.assertTrue(path.is_file())
        before={str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()}
        result=maintain(self.root,['.'],self.out,self.state)
        self.assertFalse(result['map_rebuilt']);self.assertEqual(result['changes'],[])
        self.assertEqual(before,{str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()})

    def test_native_skill_prepares_runs_and_uses_bound_scope(self):
        prepare(self.session,'architecture-maintenance','code')
        self.source.write_text(self.source.read_text().replace('x+1','x+2'))
        result=run(self.session,'architecture-maintenance',{},'code')['data']
        self.assertTrue(result['in_sync']);self.assertEqual(result['changes'][0]['type'],'modified')
        with self.assertRaises(ValueError):prepare(self.session,'architecture-maintenance','architect')

    def test_ambiguous_duplicate_content_is_not_misreported_as_rename(self):
        record={'path':'a.py','sha256':'same','symbols':[]}
        before={'files':[record,{**record,'path':'b.py'}]};after={'files':[{**record,'path':'c.py'}]}
        self.assertEqual(sorted(r['type'] for r in changes(before,after)),['added','deleted','deleted'])


def scan_empty(data):
    """Represent a source-empty baseline for addition behavior."""
    return {**data,'files':[]}
