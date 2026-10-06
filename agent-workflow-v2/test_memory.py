"""Memory distillation must be fresh, grounded, bounded and non-destructive."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from memory_draft import validate
from remember import remember, packet_for


class MemoryTests(unittest.TestCase):
    def test_grounding_limits_and_uncertainty(self):
        packet=packet_for('Proposal: keep parsing pure. One trial passed; more tests are needed. https://example.com/spec',{})
        draft={'items':[{'text':'Keep parsing pure (proposed).','evidence':'Proposal: keep parsing pure.'}]}
        self.assertIn('(proposed)',validate(draft,packet)['summary'])
        for item in [{'text':'Invented','evidence':'Absent quote'},
                     {'text':'See https://wrong.example/spec','evidence':'One trial passed'},
                     {'text':'x'*501,'evidence':'One trial passed'}]:
            with self.assertRaises(ValueError):validate({'items':[item]},packet)
        with self.assertRaises(ValueError):validate({'items':[]},packet)
        self.assertEqual(validate({'items':[],'skipped_reason':'Nothing new'},packet)['items'],[])
        with self.assertRaises(ValueError):packet_for('x'*65537,{})

    def test_failure_and_concurrent_edit_preserve_knowledge(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);root=base/'project';root.mkdir();session=base/'session';session.mkdir()
            subprocess.run(['git','init','-q',str(root)],check=True)
            note=root/'knowledge.md';note.write_text('# Existing\nKeep tests.\n')
            before=note.read_bytes()
            with self.assertRaisesRegex(ValueError,'distillation failed'):
                remember(root,'Keep parsing pure.',session,base/'shadow',base,
                         phase_fn=lambda *a:({'passed':False},None))
            self.assertEqual(note.read_bytes(),before)
            def concurrent(*args):
                note.write_text('Human changed this')
                return {'passed':True},{'items':[{'text':'Keep parsing pure.','evidence':'Keep parsing pure.'}]}
            with self.assertRaisesRegex(ValueError,'changed during'):
                remember(root,'Keep parsing pure.',session,base/'shadow',base,phase_fn=concurrent)
            self.assertEqual(note.read_text(),'Human changed this')

    def test_empty_distillation_does_not_create_a_note(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);root=base/'project';root.mkdir();session=base/'session';session.mkdir()
            result=remember(root,'Thanks!',session,base/'shadow',base,phase_fn=lambda *a:
                ({'passed':True},{'items':[],'skipped_reason':'No durable project information'}))
            self.assertTrue(result['skipped']);self.assertFalse((root/'knowledge.md').exists())


if __name__=='__main__':unittest.main()
