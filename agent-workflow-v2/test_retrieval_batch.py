"""Cross-file symbol reads remain explicit, bounded and unambiguous per file."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from retrieval_batch import read_across


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        (self.root/'one.mjs').write_text('export function first(x) { return x; }\nconst shared=1;\n')
        (self.root/'two.mjs').write_text('export function second(x) { return x*2; }\nconst shared=2;\n')

    def test_names_resolve_across_paths_without_positional_guessing(self):
        result=read_across(self.root,['one.mjs','two.mjs'],['second','first'])
        self.assertTrue(result['passed']);self.assertEqual(result['errors'],[])
        self.assertEqual([(r['path'],r['symbol']) for r in result['symbols']],
                         [('one.mjs','first'),('two.mjs','second')])

    def test_common_names_keep_both_explicit_path_labels_and_deduplicate_input(self):
        result=read_across(self.root,['one.mjs','two.mjs','one.mjs'],['shared','shared'])
        self.assertEqual(len(result['symbols']),2)
        self.assertEqual({r['path'] for r in result['symbols']},{'one.mjs','two.mjs'})

    def test_missing_and_ambiguous_names_are_not_substituted(self):
        (self.root/'two.mjs').write_text('function outer(){function same(){}}\nfunction other(){function same(){}}')
        result=read_across(self.root,['one.mjs','two.mjs'],['first','missing','same'])
        self.assertEqual(len(result['symbols']),1)
        self.assertEqual(len(result['errors']),2)
        self.assertIn('Ambiguous',result['errors'][0]['error'])
        self.assertFalse(read_across(self.root,['one.mjs'],['missing'])['passed'])

    def test_bounds_and_scope_are_checked_before_returning_source(self):
        for paths,names in [([],['first']),(['one.mjs']*6,['first']),(['one.mjs'],[]),(['one.mjs'],['first']*9)]:
            with self.assertRaises(ValueError):read_across(self.root,paths,names)
        outside=self.root.parent/(self.root.name+'-outside.mjs');outside.write_text('const secret=1;')
        self.addCleanup(outside.unlink)
        for relative in [str(outside),'missing.mjs']:
            with self.assertRaises(ValueError):read_across(self.root,['one.mjs',relative],['first','secret'])

    def test_combined_response_is_bounded_and_source_stays_unchanged(self):
        before={p.name:p.read_bytes() for p in self.root.glob('*.mjs')}
        read_across(self.root,['one.mjs','two.mjs'],['first','second'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.glob('*.mjs')})
        for name in ['one.mjs','two.mjs']:
            (self.root/name).write_text('const shared="'+'x'*7000+'";')
        with self.assertRaisesRegex(ValueError,'budget'):read_across(self.root,['one.mjs','two.mjs'],['shared'])

    def test_native_cli_dispatch(self):
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('workflow.py')),
            '--root',str(self.root),'read-symbols-across','one.mjs','two.mjs','--names','first','second'],
            capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['symbols']),2)


if __name__=='__main__':unittest.main()
