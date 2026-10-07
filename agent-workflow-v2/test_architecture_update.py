"""Verify native append/insert preservation, scope, compare-and-swap and failure recovery."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import architecture_update as updater
from project_map import scan
from shadow import refresh, verify
from skill_runner import prepare, run


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.root=base/'project';self.root.mkdir()
        self.session=base/'session';self.session.mkdir();self.doc=self.root/'architecture.md'
        self.doc.write_bytes(b'# System\r\nExisting prose.\r\n## Rules\r\nOld decision.\r\n### Child\r\nUntouched child.\r\n')
        self.state=self.session/'state.json';self.out=self.session/'shadow'
        self.contract={'before':scan(self.root,['.']),'task':{'files':['architecture.md']},'shadow':str(self.out)}
        self.state.write_text(json.dumps(self.contract))
        self.launch={'role':'code','project':str(self.root),'state':str(self.state)}
        (self.session/'launch.json').write_text(json.dumps(self.launch))
        refresh(self.root,['.'],self.out)

    def request(self,action='insert',**kwargs):
        return dict(action=action,expected_sha256=hashlib.sha256(self.doc.read_bytes()).hexdigest(),
                    section_id='system/rules',text='New deterministic rule in src/rules.py.',**kwargs)

    def test_insert_preserves_all_authored_bytes_and_crlf_before_child(self):
        original=self.doc.read_bytes();receipt=updater.update(self.session,self.request())
        changed=self.doc.read_bytes()
        self.assertIn(b'Old decision.\r\n\r\nNew deterministic rule',changed)
        self.assertIn(b'### Child\r\nUntouched child.\r\n',changed)
        self.assertEqual(changed.replace(b'\r\nNew deterministic rule in src/rules.py.\r\n\r\n',b''),original)
        self.assertNotIn(b'\n',changed.replace(b'\r\n',b''))
        self.assertEqual(receipt['after_sha256'],hashlib.sha256(changed).hexdigest())
        self.assertEqual(verify({'shadow':str(self.out)},scan(self.root,['.'])),[])

    def test_append_preserves_original_prefix_and_new_section(self):
        before=self.doc.read_bytes();request=self.request('append_section',title='Rendering')
        updater.update(self.session,request)
        self.assertTrue(self.doc.read_bytes().startswith(before))
        self.assertIn(b'## Rendering\r\n',self.doc.read_bytes())

    def test_stale_hash_second_writer_and_unknown_id_do_not_mutate(self):
        request=self.request();updater.update(self.session,request);changed=self.doc.read_bytes()
        with self.assertRaisesRegex(ValueError,'changed'):updater.update(self.session,request)
        request=self.request();request['section_id']='unknown'
        with self.assertRaisesRegex(ValueError,'Unknown'):updater.update(self.session,request)
        self.assertEqual(self.doc.read_bytes(),changed)

    def test_missing_document_creation_uses_empty_hash(self):
        self.doc.unlink();request=dict(action='append_section',expected_sha256='',title='Architecture',text='Use pure functions.')
        receipt=updater.update(self.session,request)
        self.assertEqual(receipt['before_sha256'],'')
        self.assertIn('Use pure functions.',self.doc.read_text())

    def test_empty_existing_file_requires_real_empty_file_hash(self):
        self.doc.write_bytes(b'')
        request=dict(action='append_section',expected_sha256='',title='Architecture',text='Pure rules.')
        with self.assertRaisesRegex(ValueError,'changed'):updater.update(self.session,request)
        request['expected_sha256']=hashlib.sha256(b'').hexdigest()
        updater.update(self.session,request)

    def test_scope_role_root_binding_and_symlink_reject_without_edits(self):
        original=self.doc.read_bytes()
        for modify in ['scope','role','root']:
            with self.subTest(modify=modify):
                contract=json.loads(json.dumps(self.contract));launch=dict(self.launch)
                if modify=='scope':contract['task']['files']=[]
                if modify=='role':launch['role']='architect'
                if modify=='root':contract['before']['root']=str(self.session)
                self.state.write_text(json.dumps(contract));(self.session/'launch.json').write_text(json.dumps(launch))
                with self.assertRaises(ValueError):updater.update(self.session,self.request())
                self.assertEqual(self.doc.read_bytes(),original)
        self.state.write_text(json.dumps(self.contract));(self.session/'launch.json').write_text(json.dumps(self.launch))
        self.doc.unlink();self.doc.symlink_to(self.session/'state.json')
        with self.assertRaisesRegex(ValueError,'regular'):updater.update(self.session,{'expected_sha256':''})

    def test_invalid_actions_titles_and_heading_prose_are_rejected(self):
        raw=self.doc.read_bytes()
        for overrides in [{'action':'replace'}, {'text':'# Wipe section'}, {'text':' '},
                          {'action':'append_section','title':'A\nB'}, {'text':'x'*4097}]:
            with self.subTest(overrides=overrides):
                request=self.request();request.update(overrides)
                with self.assertRaises(ValueError):updater.insertion(raw,request)
        self.assertEqual(self.doc.read_bytes(),raw)

    def test_refresh_failure_keeps_edit_and_blocks_success_receipt(self):
        original=self.doc.read_bytes()
        with patch('shadow.refresh',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):updater.update(self.session,self.request())
        self.assertNotEqual(self.doc.read_bytes(),original)
        self.assertFalse((self.session/'architecture-update.json').exists())
        self.assertTrue(verify({'shadow':str(self.out)},scan(self.root,['.'])))
        refresh(self.root,['.'],self.out)
        self.assertEqual(verify({'shadow':str(self.out)},scan(self.root,['.'])),[])

    def test_fixed_native_skill_pipeline_writes_bound_document(self):
        prepared=prepare(self.session,'architecture-update','code')
        request=self.request()
        request['expected_sha256']=prepared['architecture_revision']['expected_sha256']
        result=run(self.session,'architecture-update',request,'code')
        self.assertEqual(result['data']['after_sha256'],hashlib.sha256(self.doc.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):prepare(self.session,'architecture-update','inspect')

    def test_preparation_exposes_only_bound_revision_without_rewriting_project_or_shadow(self):
        paths=[self.doc,*[p for p in self.out.rglob('*') if p.is_file()]]
        before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in paths}
        prepared=prepare(self.session,'architecture-update','code')
        revision=prepared['architecture_revision']
        self.assertEqual(revision,{'path':'architecture.md','exists':True,
                                  'expected_sha256':hashlib.sha256(self.doc.read_bytes()).hexdigest()})
        self.assertNotEqual(prepared['sha256'],revision['expected_sha256'])
        self.assertNotIn('Existing prose',json.dumps(prepared))
        self.assertEqual(before,{str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in paths})

    def test_preparation_distinguishes_missing_and_empty_documents(self):
        self.doc.unlink()
        missing=prepare(self.session,'architecture-update','code')['architecture_revision']
        self.assertEqual(missing,{'path':'architecture.md','exists':False,'expected_sha256':''})
        self.doc.write_bytes(b'')
        empty=prepare(self.session,'architecture-update','code')['architecture_revision']
        self.assertEqual(empty,{'path':'architecture.md','exists':True,'expected_sha256':hashlib.sha256(b'').hexdigest()})

    def test_preparation_rejects_scope_role_root_and_nonregular_documents(self):
        for modification in ['scope','role','root']:
            with self.subTest(modification=modification):
                contract=json.loads(json.dumps(self.contract));launch=dict(self.launch)
                if modification=='scope':contract['task']['files']=[]
                if modification=='role':launch['role']='architect'
                if modification=='root':contract['before']['root']=str(self.session)
                self.state.write_text(json.dumps(contract));(self.session/'launch.json').write_text(json.dumps(launch))
                with self.assertRaises(ValueError):prepare(self.session,'architecture-update','code')
                self.assertFalse((self.session/'skill-prepared/architecture-update.json').exists())
        self.state.write_text(json.dumps(self.contract));(self.session/'launch.json').write_text(json.dumps(self.launch))
        self.doc.unlink();self.doc.symlink_to(self.state)
        with self.assertRaisesRegex(ValueError,'regular'):prepare(self.session,'architecture-update','code')
        self.doc.unlink();self.doc.mkdir()
        with self.assertRaisesRegex(ValueError,'regular'):prepare(self.session,'architecture-update','code')

    def test_direct_editor_race_is_detected_before_replace(self):
        original_chmod=updater.os.chmod
        def race(path,mode):
            original_chmod(path,mode);self.doc.write_text('# Manually changed\n')
        with patch('architecture_update.os.chmod',side_effect=race):
            with self.assertRaisesRegex(ValueError,'during insertion'):updater.update(self.session,self.request())
        self.assertEqual(self.doc.read_text(),'# Manually changed\n')
        self.assertFalse(list(self.root.glob('.mypi-architecture-*')))

    def test_two_native_writers_with_same_hash_accept_exactly_one_insertion(self):
        code='import json,sys; from pathlib import Path; from architecture_update import update; print(json.dumps(update(Path(sys.argv[1]),json.loads(sys.argv[2]))))'
        request=json.dumps(self.request())
        argv=[sys.executable,'-c',code,str(self.session),request]
        workers=[subprocess.Popen(argv,cwd=Path(__file__).parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        outputs=[p.communicate(timeout=20) for p in workers]
        self.assertEqual(sorted(p.returncode for p in workers),[0,1])
        self.assertEqual(self.doc.read_text().count('New deterministic rule'),1)
        self.assertTrue(any(b'Architecture changed' in err for _,err in outputs))
