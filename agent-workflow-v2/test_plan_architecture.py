"""New workers get exact planned interfaces; existing architecture remains untouched."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from plan_architecture import sectioned, bootstrap


class ArchitectureSeedTests(unittest.TestCase):
    def test_failed_publish_leaves_no_partial_architecture_or_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plan={'architecture':'Full planned API.','tasks':[{'files':['architecture.md']}]}
            with patch('plan_architecture.os.link',side_effect=OSError('Filesystem unavailable')):
                with self.assertRaises(OSError):bootstrap(root,plan)
            self.assertEqual(list(root.iterdir()),[])

    def test_concurrent_publish_creates_exactly_one_complete_document(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plans=[{'architecture':label*1000,'tasks':[{'files':['architecture.md']}]} for label in ['First.','Second.']]
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda plan:bootstrap(root,plan),plans))
            self.assertEqual(sum(r['created'] for r in results),1)
            self.assertIn((root/'architecture.md').read_text(),[sectioned(p['architecture']) for p in plans])
            self.assertEqual([p.name for p in root.iterdir()],['architecture.md'])
    def test_plain_api_contracts_gain_sections_without_losing_lines(self):
        original='WORLD: grid.\n- src/engine/rng.mjs: seeded(rng).\n- src/ui/main.mjs: initGame(canvas).\nINVARIANTS: no DOM in engine.'
        result=sectioned(original)
        for line in original.splitlines():self.assertIn(line,result.splitlines())
        self.assertIn('## src/engine/rng.mjs',result)
        self.assertIn('## Invariants',result)
        self.assertEqual(sectioned('# Existing\nDecision.'),'# Existing\nDecision.')

    def test_create_once_existing_crlf_and_unscoped_plan_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plan={'architecture':'Exact API.','tasks':[{'files':['architecture.md']}]}
            self.assertTrue(bootstrap(root,plan)['created'])
            first=(root/'architecture.md').read_bytes()
            self.assertIn(b'Exact API.',first)
            self.assertFalse(bootstrap(root,{**plan,'architecture':'Different'})['created'])
            self.assertEqual((root/'architecture.md').read_bytes(),first)
            (root/'architecture.md').write_bytes(b'# Authored\r\nKeep this.\r\n')
            self.assertFalse(bootstrap(root,plan)['created'])
            self.assertEqual((root/'architecture.md').read_bytes(),b'# Authored\r\nKeep this.\r\n')
            (root/'architecture.md').unlink()
            self.assertFalse(bootstrap(root,{**plan,'tasks':[{'files':['README.md']}]})['created'])
            self.assertFalse((root/'architecture.md').exists())

    def test_symlink_and_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);plan={'architecture':'API.','tasks':[{'files':['architecture.md']}]}
            target=root/'outside';target.write_text('Keep');(root/'architecture.md').symlink_to(target)
            with self.assertRaises(ValueError):bootstrap(root,plan)
            self.assertEqual(target.read_text(),'Keep')
            (root/'architecture.md').unlink();(root/'architecture.md').mkdir()
            with self.assertRaises(ValueError):bootstrap(root,plan)

    def test_seeded_sections_associate_files_for_selective_worker_packet(self):
        import architecture_sections
        from project_map import scan
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'src/engine').mkdir(parents=True)
            (root/'src/engine/rng.mjs').write_text('/** deterministic generator */\nexport function seeded(seed) {return () => seed;}')
            (root/'src/ui').mkdir();(root/'src/ui/main.mjs').write_text('export function initGame(canvas) {return canvas;}')
            plan={'architecture':'- src/engine/rng.mjs: seeded(seed).\n- src/ui/main.mjs: initGame(canvas).',
                  'tasks':[{'files':['architecture.md']}]}
            bootstrap(root,plan);data=scan(root,['.']);sections=architecture_sections.build(data)['sections']
            rng=[row for row in sections if row['title']=='src/engine/rng.mjs'][0]
            self.assertIn('src/engine/rng.mjs',rng['files'])
            self.assertNotIn('src/ui/main.mjs',rng['files'])

    def test_future_module_contract_is_prefetched_before_source_exists(self):
        import json
        import prefetch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'project';root.mkdir();state=Path(folder)/'state.json'
            state.write_text(json.dumps({'readonly_tests':{}}))
            text='Layering: '+('Bounded guidance. '*550)+'\n- src/engine/rng.mjs: mulberry32(seed) -> seeded generator.\n- src/ui/main.mjs: initGame(canvas).'
            task={'files':['src/engine/rng.mjs','architecture.md'],'context':{}}
            bootstrap(root,{'architecture':text,'tasks':[task]})
            packet=prefetch.packet(root,['.'],task,state)
            self.assertIn('mulberry32(seed) -> seeded generator.',packet)
            self.assertNotIn('initGame(canvas).',packet)
