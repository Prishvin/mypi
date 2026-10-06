"""Exercise every-edit architecture maintenance and atomic todo context integration."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import architecture_sync as syncer
import architecture_sections
from project_map import scan
from tasks import begin, check, run_tests
from shadow import refresh, verify
from prefetch import packet
from plans import validate_context
from skill_runner import prepare, run


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'project';self.root.mkdir()
        self.session=self.base/'session';self.session.mkdir();self.state=self.session/'state.json'
        self.source=self.root/'logic.py';self.source.write_text('def step(x):\n    """Advance by one."""\n    return x+1\n')
        self.doc=self.root/'architecture.md';self.authored=b'# Domain\r\nKeep logic.py pure.\r\n## Rendering\r\nDo not couple UI.\r\n'
        self.doc.write_bytes(self.authored)
        task={'goal':'Add new rule','files':['logic.py'],'acceptance':['Rule returns correct result'],
              'tests':[[sys.executable,'-c','from logic import step; assert step(1)==3']],
              'context':{'interfaces':[],'symbols':[],'reference_files':[],
                         'max_input_tokens':8192,'max_output_tokens':4096}}
        self.contract=begin(self.root,['.'],task,self.state)
        (self.session/'launch.json').write_text(json.dumps({'project':str(self.root),'role':'code','state':str(self.state),'shadow':self.contract['shadow'],'prefixes':['.']}))

    def edit(self):
        self.source.write_text('class Rules:\n    """Pure rules."""\n    pass\ndef step(x):\n    """Advance by two."""\n    return x+2\n')

    def test_scope_reserved_before_edit_and_no_initial_source_mutation(self):
        self.assertIn('architecture.md',self.contract['task']['files'])
        self.assertEqual(self.doc.read_bytes(),self.authored)
        self.assertFalse(syncer.sync(self.state))
        self.assertEqual(self.doc.read_bytes(),self.authored)
        task={'files':[f'x{i}.py' for i in range(8)]}
        with self.assertRaisesRegex(ValueError,'Reserve'):syncer.scoped(task)

    def test_edit_updates_interfaces_preserves_prose_and_is_idempotent(self):
        self.edit();self.assertTrue(syncer.sync(self.state));raw=self.doc.read_bytes()
        self.assertTrue(raw.startswith(self.authored))
        self.assertEqual(raw.count(syncer.START.encode()),1)
        self.assertIn(b'"Rules"',raw);self.assertIn(b'"step"',raw)
        self.assertNotIn(b'return x+2',raw)
        self.assertFalse(syncer.sync(self.state));self.assertEqual(self.doc.read_bytes(),raw)
        self.assertEqual(syncer.verify(self.contract,scan(self.root,['.'])),[])

    def test_second_edit_replaces_only_owned_record_and_updates_signature_names(self):
        self.edit();syncer.sync(self.state)
        self.source.write_text('def advance(x):\n    """Advance by two."""\n    return x+2\n')
        self.assertTrue(syncer.sync(self.state));text=self.doc.read_text()
        owned,_=syncer.records(text)
        self.assertEqual(owned['logic.py']['functions'],['advance'])
        self.assertEqual(owned['logic.py']['classes'],[])
        self.assertTrue(self.doc.read_bytes().startswith(self.authored))
        self.assertEqual(text.count(syncer.START),1)

    def test_deleted_file_and_parse_failure_are_explicit(self):
        self.source.write_text('def broken(:\n')
        syncer.sync(self.state);record=syncer.records(self.doc.read_text())[0]['logic.py']
        self.assertIsNotNone(record['parse_error'])
        self.source.unlink();syncer.sync(self.state)
        self.assertEqual(syncer.records(self.doc.read_text())[0]['logic.py'],{'deleted':True})

    def test_stale_architecture_and_shadow_block_gate_until_refresh_and_tests(self):
        self.edit();self.assertTrue(syncer.verify(self.contract,scan(self.root,['.'])))
        self.assertFalse(check(self.state)['passed'])
        run_tests(self.state)  # Includes architecture maintenance before test snapshot.
        self.assertTrue(check(self.state)['passed'],check(self.state))
        out=Path(self.contract['shadow']);index=json.loads((out/'architecture-map.json').read_text())
        vocabulary=architecture_sections.artifact(index)
        self.assertIn('Rules',vocabulary);self.assertIn('logic.py',vocabulary)
        self.source.write_text(self.source.read_text().replace('x+2','x+3'))
        self.assertFalse(check(self.state)['passed'])

    def test_required_decision_insert_blocks_even_when_automatic_metadata_is_current(self):
        contract=json.loads(self.state.read_text());contract['task']['context']['architecture_update_required']=True
        self.state.write_text(json.dumps(contract));self.edit();run_tests(self.state)
        self.assertFalse(check(self.state)['passed'])
        prepare(self.session,'architecture-update','code')
        run(self.session,'architecture-update',{'action':'insert','section_id':'domain',
            'expected_sha256':hashlib.sha256(self.doc.read_bytes()).hexdigest(),'text':'Rules now advance by two.'},'code')
        run_tests(self.state);self.assertTrue(check(self.state)['passed'],check(self.state))
        self.doc.write_bytes(self.doc.read_bytes()+b'Extra decision.\n');run_tests(self.state)
        self.assertFalse(check(self.state)['passed'])

    def test_invalid_owned_markers_and_dangling_symlinks_never_overwrite(self):
        self.edit();self.doc.write_text('# Domain\n'+syncer.START+'\nbroken')
        raw=self.doc.read_bytes()
        with self.assertRaisesRegex(ValueError,'Malformed'):syncer.sync(self.state)
        self.assertEqual(self.doc.read_bytes(),raw)
        self.doc.unlink();self.doc.symlink_to(self.base/'missing')
        with self.assertRaisesRegex(ValueError,'regular'):syncer.sync(self.state)

    def test_packet_reloads_only_pinned_sections_and_rejects_stale_reference(self):
        text='# Domain\nlogic.py pure rules.\n## Wanted\nSmall contract.\n## Unrelated\n'+('UNRELATED_LONG_TEXT\n'*1500)
        self.doc.write_text(text);data=scan(self.root,['.']);sha=data['architecture']['sha256']
        task=json.loads(self.state.read_text())['task']
        task['context']['architecture_sections']=[{'id':'domain/wanted','sha256':sha}]
        validate_context(self.root,task)
        context=packet(self.root,['.'],task,self.state)
        self.assertIn('Small contract.',context);self.assertNotIn('UNRELATED_LONG_TEXT',context)
        self.doc.write_text('Inserted preamble\n'+text)
        with self.assertRaisesRegex(ValueError,'changed'):packet(self.root,['.'],task,self.state)
        with self.assertRaisesRegex(ValueError,'changed'):validate_context(self.root,task)

    def test_oversized_selected_section_is_not_silently_omitted(self):
        self.doc.write_text('# Huge\n'+('Long contract.\n'*2000))
        task=json.loads(self.state.read_text())['task'];sha=hashlib.sha256(self.doc.read_bytes()).hexdigest()
        task['context']['architecture_sections']=[{'id':'huge','sha256':sha}]
        with self.assertRaisesRegex(ValueError,'budget'):packet(self.root,['.'],task,self.state,limit=4000)

    def test_navigation_skill_build_search_and_section_pipeline_never_changes_source(self):
        before=self.doc.read_bytes();prepare(self.session,'architecture-navigation','inspect')
        result=run(self.session,'architecture-navigation',{'action':'index'},'inspect')
        self.assertIn('domain',result['data']['index_page'])
        hits=run(self.session,'architecture-navigation',{'action':'search','query':'step'},'inspect')['data']
        self.assertTrue(any(row.get('path')=='logic.py' for row in hits['matches']))
        result=run(self.session,'architecture-navigation',{'action':'section','section_id':'domain',
            'sha256':hashlib.sha256(before).hexdigest()},'inspect')
        self.assertIn('Keep logic.py pure.',result['data']['text'])
        self.assertEqual(self.doc.read_bytes(),before)

    def test_partial_failure_can_resume_and_regenerate_stale_owned_artifacts(self):
        self.edit();syncer.sync(self.state)
        with patch('shadow.refresh',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):run_tests(self.state)
        self.assertFalse(check(self.state)['passed'])
        run_tests(self.state);self.assertTrue(check(self.state)['passed'],check(self.state))
        self.assertEqual(verify(self.contract,scan(self.root,['.'])),[])

    def test_todo_section_hash_survives_unrelated_edits_and_automatic_metadata(self):
        self.doc.write_text('# Domain\n## Rules\nlogic.py owns pure decisions.\n## UI\nSeparate adapter.\n')
        data=scan(self.root,['.']);index=architecture_sections.build(data)
        row=next(r for r in index['sections'] if r['id']=='domain/rules')
        task=json.loads(self.state.read_text())['task']
        task['context']['architecture_sections']=[{'id':row['id'],'sha256':row['content_sha256']}]
        self.edit();syncer.sync(self.state)
        validate_context(self.root,task)
        self.assertIn('logic.py owns pure decisions.',packet(self.root,['.'],task,self.state))
        self.doc.write_text('Inserted preamble\n'+self.doc.read_text().replace('Separate adapter.','Changed unrelated UI.'))
        validate_context(self.root,task)
        self.doc.write_text(self.doc.read_text().replace('pure decisions.','different decisions.'))
        with self.assertRaisesRegex(ValueError,'section changed'):packet(self.root,['.'],task,self.state)
