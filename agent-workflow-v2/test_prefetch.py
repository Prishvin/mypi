"""Check that task packets expose selected code and immutable fixtures only."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tasks import begin
from prefetch import packet, module_literals


class PrefetchTests(unittest.TestCase):
    """Use an actual tiny Git project and an external acceptance fixture."""
    def test_browser_skill_is_loaded_only_for_browser_boundary_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'project';root.mkdir();state=Path(folder)/'state.json'
            state.write_text(json.dumps({'readonly_tests':{}}))
            pure=packet(root,['.'],{'files':['src/engine/math.mjs'],'context':{}},state)
            browser=packet(root,['.'],{'files':['src/ui/input.mjs'],'context':{}},state)
            self.assertNotIn('Mouse displacement',pure)
            self.assertIn('Mouse displacement',browser)
            self.assertIn('TASK SKILL browser-interaction-review',browser)
    def test_selected_functions_and_literals_exclude_unrelated_bodies(self):
        """The packet carries its recipe without expanding to the whole module."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'repo'
            root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'a.js').write_text('const STEP=1;\nconst object={hidden:"value"};\n'
                '/** Increment once. */\nexport function step(x){return x+STEP;}\n'
                '/** Unrelated. */\nexport function other(){return "UNRELATED_IMPLEMENTATION";}')
            fixture = Path(folder) / 'acceptance.mjs'
            fixture.write_text('assert.equal(step(1),2);')
            (root / 'editable.js').write_text('/** Editable unit. */\nfunction run(){return "EDITABLE_BODY";}')
            task = {'goal':'Fix step','files':['editable.js'],'acceptance':['Increments'],
                    'tests':[['node',str(fixture)]],
                    'context':{'interfaces':['a.js'],'symbols':[{'path':'a.js','name':'step'}]}}
            state = Path(folder) / 'state.json'
            begin(root,['.'],task,state)
            result = packet(root,['.'],task,state)
            self.assertIn('return x+STEP',result)
            self.assertIn('const STEP=1;',result)
            self.assertIn('assert.equal(step(1),2)',result)
            self.assertIn('EDITABLE_BODY',result)
            self.assertNotIn('UNRELATED_IMPLEMENTATION',result)
            self.assertEqual(module_literals(root,'a.js'),['const STEP=1;'])
            self.assertNotIn('return x+STEP',packet(root,['.'],task,state,limit=100))

    def test_focused_packet_keeps_import_contract_without_unrelated_implementation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir()
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'view.js').write_text('import {raycast} from "./engine.js";\n/** Render injected view. */\nexport function render(ctx,w){return ctx;}\n/** Unrelated helper. */\nfunction unused(){return "UNRELATED_BODY";}')
            task={'goal':'Render','files':['view.js'],'acceptance':['Draws'], 'tests':[['node','--version']],
                  'context':{'interfaces':['view.js'],'symbols':[{'path':'view.js','name':'render'}],'selected_symbols_only':True}}
            state=Path(folder)/'state.json';begin(root,['.'],task,state)
            result=packet(root,['.'],task,state)
            self.assertIn('raycast',result);self.assertIn('./engine.js',result)
            self.assertIn('return ctx',result);self.assertNotIn('UNRELATED_BODY',result)

    def test_unmatched_case_patterns_fall_back_to_pinned_fixture_page(self):
        """An uncertain planner pattern must not silently hide acceptance evidence."""
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir()
            subprocess.run(['git','init','-q',str(root)],check=True)
            fixture=Path(folder)/'acceptance.mjs'
            fixture.write_text("test('actual behavior',()=>assert.equal(1,1));\n")
            task={'goal':'Implement','files':['new.mjs'],'acceptance':['Correct behavior'],
                  'tests':[['node',str(fixture)]],'context':{
                      'selected_symbols_only':True,'fixture_test_patterns':['nonexistent case']}}
            state=Path(folder)/'state.json';begin(root,['.'],task,state)
            result=packet(root,['.'],task,state)
            self.assertIn('no case pattern matched',result)
            self.assertIn('actual behavior',result)

    def test_planned_new_files_are_creation_contracts_not_missing_retrievals(self):
        """Absent declared files must not send the worker on an impossible lookup."""
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir()
            subprocess.run(['git','init','-q',str(root)],check=True)
            task={'goal':'Create a module','files':['new.mjs'],'acceptance':['Correct behavior'],
                  'tests':[['node','--version']],'context':{'selected_symbols_only':True,
                      'interfaces':['new.mjs'],'symbols':[{'path':'new.mjs','name':'run'}],
                      'reference_files':['new.mjs']}}
            state=Path(folder)/'state.json';begin(root,['.'],task,state)
            result=packet(root,['.'],task,state)
            self.assertIn('PLANNED NEW FILES',result)
            self.assertIn('Do not search for nonexistent implementations',result)
            self.assertNotIn('Unknown source paths: new.mjs',result)
            self.assertTrue(result.endswith('retrieval: []'))


if __name__ == '__main__':
    unittest.main()
