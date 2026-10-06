"""Focused packets keep exact pinned tests and omit unrelated implementations."""
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from prefetch import packet


class FocusedPackets(unittest.TestCase):
    def test_named_symbols_and_matching_tests_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'app').mkdir()
            (root/'app/unit.js').write_text('/** chosen */\nexport function chosen(){return 1;}\n/** other */\nexport function other(){return "UNRELATED_IMPLEMENTATION";}\n')
            fixture=root/'fixture.mjs'
            fixture.write_text('import test from "node:test";\ntest("chosen behavior",()=>{const x=1;});\ntest("other behavior",()=>{const x="UNRELATED_TEST";});\n')
            state=root/'state.json'
            state.write_text(json.dumps({'readonly_tests':{str(fixture):hashlib.sha256(fixture.read_bytes()).hexdigest()}}))
            task={'files':['app/unit.js'],'context':{'selected_symbols_only':True,
                'symbols':[{'path':'app/unit.js','name':'chosen'}],
                'interfaces':['app/unit.js'],'fixture_test_patterns':['chosen behavior']}}
            text=packet(root,['app'],task,state)
            self.assertIn('chosen(){return 1;}',text)
            self.assertIn('chosen behavior',text)
            self.assertNotIn('UNRELATED_IMPLEMENTATION',text)
            self.assertNotIn('UNRELATED_TEST',text)
            self.assertIn(hashlib.sha256(fixture.read_bytes()).hexdigest(),text)

    def test_changed_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();fixture=root/'fixture.mjs';fixture.write_text('test("chosen",()=>{});')
            subprocess.run(['git','init','-q',str(root)],check=True)
            state=root/'state.json';state.write_text(json.dumps({'readonly_tests':{str(fixture):'incorrect'}}))
            with self.assertRaises(ValueError):
                packet(root,[],{'files':[],'context':{'selected_symbols_only':True,'fixture_test_patterns':['chosen']}},state)


if __name__=='__main__':unittest.main()
