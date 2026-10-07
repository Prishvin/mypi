"""Sparse JSON failures stay strict and point to the original malformed value."""
import copy
import json
import unittest
from plan_patch_transport import decode, container_hint


class PatchTransportTests(unittest.TestCase):
    def test_exact_arrays_serialized_arrays_and_joined_parameters_preserve_data(self):
        plain={'task_updates':[{'id':'A','steps':['First','Second']}],
               'architecture_replacements':[{'old':'one','new':'two'}]}
        for encoded in (plain,{k:json.dumps(v) for k,v in plain.items()},
                        {'task_updates':json.dumps(plain)[len('{"task_updates": '):-1]}):
            before=copy.deepcopy(encoded);result,notes=decode(encoded)
            self.assertEqual(result,plain);self.assertEqual(encoded,before)
            self.assertEqual(bool(notes),encoded!=plain)

    def test_mismatched_closer_reports_actual_offset_field_and_container(self):
        raw='[{"id":"A","replace_with":[{"id":"A1","steps":["First","Second"}],{"id":"A"}]}]'
        with self.assertRaises(json.JSONDecodeError) as original:json.loads(raw)
        patch={'task_updates':raw};before=copy.deepcopy(patch)
        with self.assertRaises(ValueError) as caught:decode(patch)
        error=str(caught.exception)
        self.assertIn(f'task_updates contains malformed JSON at character {original.exception.pos}',error)
        self.assertIn("needs ']' before '}'",error)
        self.assertIn('Nearby text',error);self.assertLess(len(error),700)
        self.assertEqual(patch,before)

    def test_multiline_and_unicode_offsets_are_for_original_not_wrapped_value(self):
        raw='[\n {"id":"é", "steps":["first" "second"]}\n]'
        with self.assertRaises(json.JSONDecodeError) as original:json.loads(raw)
        with self.assertRaises(ValueError) as caught:decode({'task_updates':raw})
        error=original.exception
        self.assertIn(f'character {error.pos} (line {error.lineno}, column {error.colno})',str(caught.exception))

    def test_joined_second_parameter_error_has_original_offset(self):
        raw='[{"id":"A"}], "architecture_replacements":[{"old":"a", "new":"b"}] trailing'
        with self.assertRaises(ValueError) as caught:decode({'task_updates':raw})
        self.assertIn(f'character {raw.index("trailing")}',str(caught.exception))
        self.assertNotIn('During handling',str(caught.exception))

    def test_string_braces_escaped_quotes_and_backslashes_do_not_fake_a_mismatch(self):
        data={'id':'A','steps':['Literal } ] [ {', 'Escaped " quote \\ and ]']}
        raw=json.dumps([data])
        self.assertEqual(container_hint(raw,len(raw)),'')
        self.assertEqual(decode({'task_updates':raw})[0]['task_updates'],[data])
        with self.assertRaises(ValueError) as caught:decode({'task_updates':'[{"id":"A"})]'} )
        self.assertIn('not parentheses',str(caught.exception))

    def test_rejects_duplicate_nonfinite_deep_and_oversized_encoded_values(self):
        bad=['[{"id":"A","id":"B"}]','[{"id":"A","x":NaN}]',
             '[{"id":"A","x":Infinity}]', '['*1100+'0'+']'*1100,
             '[{"id":"'+'é'*524288+'"}]', '[{"id":"A"}],"architecture_replacements":[{"x":NaN}]']
        for value in bad:
            with self.subTest(prefix=value[:50]),self.assertRaises(ValueError):decode({'task_updates':value})

    def test_array_shapes_and_joined_conflicts_remain_rejected(self):
        for field in ('task_updates','architecture_replacements'):
            for value in (None,{},1,[None],['{}'],'{}','["{}"]','"[]"'):
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):decode({field:value})
        for patch in ([],None,{'task_updates':'[], "goal":"hidden"'},
                      {'task_updates':'[], "task_updates":[]'},
                      {'task_updates':'[], "architecture_replacements":[]','architecture_replacements':[]}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):decode(patch)

    def test_error_excerpt_is_bounded_even_for_large_fields(self):
        raw='[{"id":"A","steps":["'+'x'*60000+'"}]'
        with self.assertRaises(ValueError) as caught:decode({'task_updates':raw})
        self.assertLess(len(str(caught.exception)),700)
        self.assertNotIn('x'*200,str(caught.exception))
