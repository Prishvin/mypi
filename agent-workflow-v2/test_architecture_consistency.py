"""Prove stale checks are read-only and the fixed rebuild skill repairs bound evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from architecture_consistency import check, rebuild
from project_map import scan
from shadow import refresh
from skill_runner import prepare, run
from tasks import begin


class ConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name).resolve();self.root=base/'project';self.root.mkdir()
        self.session=base/'session';self.session.mkdir();self.output=self.session/'shadow'
        self.source=self.root/'logic.py';self.source.write_text('def answer():\n    """Return a result."""\n    return 1\n')
        self.doc=self.root/'architecture.md';self.doc.write_text('# Rules\nlogic.py owns answers.\n')
        self.launch={'project':str(self.root),'prefixes':['.'],'shadow':str(self.output),'role':'inspect','state':None}
        (self.session/'launch.json').write_text(json.dumps(self.launch))
        refresh(self.root,['.'],self.output)

    def test_fresh_check_returns_no_question_and_does_not_write_any_artifact(self):
        before={str(p):p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        report=check(self.root,['.'],self.output)
        self.assertTrue(report['in_sync']);self.assertIsNone(report['question'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.output.rglob('*') if p.is_file()})

    def test_external_source_or_architecture_edit_is_reported_without_repair(self):
        for target,text in [(self.source,'def another():\n    """Answer differently."""\n    return 2\n'),
                            (self.doc,'# Different architecture\nlogic.py remains pure.\n')]:
            with self.subTest(target=target):
                original=(self.output/'manifest.json').read_bytes();target.write_text(text)
                report=check(self.root,['.'],self.output)
                self.assertTrue(report['rebuild_required']);self.assertIn('/rebuild',report['question'])
                self.assertEqual((self.output/'manifest.json').read_bytes(),original)
                self.assertTrue(rebuild(self.root,['.'],self.output)['check']['in_sync'])
                self.assertEqual(target.read_text(),text)

    def test_missing_corrupt_map_and_prototype_are_detected_and_repaired(self):
        for relative in ['architecture-map.json','architecture-map.md','prototypes/logic.py.txt','manifest.json']:
            with self.subTest(relative=relative):
                path=self.output/relative;path.unlink()
                self.assertTrue(check(self.root,['.'],self.output)['rebuild_required'])
                result=rebuild(self.root,['.'],self.output)
                self.assertTrue(result['check']['in_sync']);self.assertTrue(path.is_file())
                path.write_text('corrupt')
                self.assertFalse(check(self.root,['.'],self.output)['in_sync'])
                rebuild(self.root,['.'],self.output)

    def test_skill_check_then_rebuild_uses_real_bound_project_and_artifacts(self):
        prepare(self.session,'architecture-sync-check','inspect')
        self.source.write_text('def answer():\n    """Return another result."""\n    return 2\n')
        report=run(self.session,'architecture-sync-check',{'action':'check'},'inspect')['data']
        self.assertTrue(report['rebuild_required'])
        result=run(self.session,'architecture-sync-check',{'action':'rebuild'},'inspect')['data']
        self.assertTrue(result['rebuilt']);self.assertTrue(result['check']['in_sync'])
        self.assertTrue(self.doc.read_text().startswith('# Rules\nlogic.py owns answers.\n'))
        self.assertIn('answer', self.doc.read_text())
        with self.assertRaises(Exception):run(self.session,'architecture-sync-check',{'action':'rebuild','project':'/tmp'},'inspect')

    def test_coding_rebuild_updates_maintained_architecture_and_preserves_prose(self):
        state=self.session/'state.json'
        contract=begin(self.root,['.'],{'goal':'Change answer','files':['logic.py'],'acceptance':['Returns 2'],
            'tests':[[sys.executable,'-c','assert True']]},state,self.output)
        self.launch.update(role='code',state=str(state));(self.session/'launch.json').write_text(json.dumps(self.launch))
        authored=self.doc.read_bytes();self.source.write_text('def answer():\n    """Return another result."""\n    return 2\n')
        report=check(self.root,['.'],self.output,state)
        self.assertTrue(any('interface record' in reason for reason in report['reasons']))
        prepare(self.session,'architecture-sync-check','code')
        result=run(self.session,'architecture-sync-check',{'action':'rebuild'},'code')['data']
        self.assertTrue(result['check']['in_sync']);self.assertTrue(self.doc.read_bytes().startswith(authored))

    def test_failed_rebuild_returns_no_false_success(self):
        self.source.write_text(self.source.read_text().replace('return 1','return 2'))
        with patch('shadow.refresh',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):rebuild(self.root,['.'],self.output)
        self.assertFalse(check(self.root,['.'],self.output)['in_sync'])

    def test_wrong_project_or_output_binding_rejects_before_source_update(self):
        state=self.session/'wrong-state.json'
        state.write_text(json.dumps({'before':{'root':str(self.root)},'shadow':str(self.output/'wrong')}))
        raw=self.doc.read_bytes()
        with self.assertRaisesRegex(ValueError,'binding'):rebuild(self.root,['.'],self.output,state)
        self.assertEqual(self.doc.read_bytes(),raw)

    def test_readonly_rebuild_repairs_stale_owned_metadata_after_external_edit(self):
        self.source.write_text(self.source.read_text().replace('return 1','return 2'))
        rebuild(self.root,['.'],self.output)
        authored=self.doc.read_text().split('## Maintained shadow interfaces')[0]
        self.source.write_text('def replacement():\n    """Return another result."""\n    return 3\n')
        refresh(self.root,['.'],self.output)
        self.assertTrue(any('interface is stale' in r for r in check(self.root,['.'],self.output)['reasons']))
        prepare(self.session,'architecture-sync-check','inspect')
        result=run(self.session,'architecture-sync-check',{'action':'rebuild'},'inspect')['data']
        self.assertTrue(result['check']['in_sync'])
        self.assertTrue(self.doc.read_text().startswith(authored))
        self.assertIn('replacement',self.doc.read_text())
        self.assertIn('return 3',self.source.read_text())
