"""Finite source modules remain loadable without imposing limits on architecture prose."""
import tempfile
import unittest
from pathlib import Path
from file_size import source_tokens
from project_map import scan,outline
from policy import validate_change
from prefetch import editable_files


class FileSizeTests(unittest.TestCase):
    def record(self,sha,tokens):
        return {'path':'data.mjs','sha256':sha,'lines':2,'bytes':16000,'source_tokens':tokens,'symbols':[]}
    def test_token_limit_is_independent_of_short_line_and_byte_counts(self):
        small=self.record('a',8192);large=self.record('b',8193)
        self.assertTrue(validate_change({'files':[]},{'files':[small]},['data.mjs'])['passed'])
        result=validate_change({'files':[]},{'files':[large]},['data.mjs'])
        self.assertFalse(result['passed']);self.assertIn('8192 source tokens',' '.join(result['violations']))
    def test_large_legacy_file_may_shrink_but_not_grow(self):
        before={'files':[self.record('a',10000)]}
        for tokens,passed in [(9900,True),(10000,True),(10001,False)]:
            result=validate_change(before,{'files':[self.record('b',tokens)]},['data.mjs'])
            self.assertEqual(result['passed'],passed)
    def test_real_token_measurements_in_shadow_and_architecture_has_no_source_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);text='const value = 42;\n';(root/'small.mjs').write_text(text)
            (root/'architecture.md').write_text('# Existing\n'+'Long decisions\n'*500)
            data=scan(root,['.']);record=data['files'][0]
            self.assertEqual(record['source_tokens'],source_tokens(text));self.assertIn('source tokens',outline(record))
            self.assertTrue(validate_change({'files':[]},data,['small.mjs','architecture.md'])['passed'])
    def test_oversized_file_is_not_prefetched_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data.mjs').write_text('const data=['+','.join(str(i) for i in range(5000))+'];')
            called=[];self.assertGreater(source_tokens((root/'data.mjs').read_text()),8192)
            self.assertEqual(editable_files(root,{'files':['data.mjs']},lambda *a:called.append(a)),set())
            self.assertEqual(called,[])


if __name__=='__main__':unittest.main()
