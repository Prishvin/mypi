"""Exercise real section boundaries, compact vocabulary and stale bounded retrieval."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import architecture_sections as sections
import architecture_map
from project_map import scan, write_map
import shadow


def fixture(text):
    """Supply complete small interface records with no implementation in the map."""
    return {'snapshot': 'snapshot', 'architecture': {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()},
            'files': [{'path': 'src/rules.py', 'description':'Pure game rules.', 'symbols':
                       [{'kind':'class', 'name':'Game'}, {'kind':'function', 'name':'Game.move'}],
                       'variables':[{'name':'BOARD_SIZE'}], 'imports':['typing']},
                      {'path':'ui/view.js', 'description':'UI.', 'symbols':[{'kind':'function','name':'drawBoard'}]}]}


class SectionTests(unittest.TestCase):
    def test_nested_ranges_direct_body_and_stable_ids_after_inserted_prose(self):
        text = 'Intro\n# System\nDecision\n## Rules\nsrc/rules.py\n### Moves\nDetails\n## UI\nui/view.js\n'
        rows = sections.parse(text)
        self.assertEqual([r['id'] for r in rows], ['preamble','system','system/rules','system/rules/moves','system/ui'])
        self.assertEqual((rows[2]['start_line'],rows[2]['end_line'],rows[2]['direct_end_line']), (4,7,5))
        moved = sections.parse(text.replace('Decision\n','Decision\nExtra rationale\n'))
        self.assertEqual([r['id'] for r in moved], [r['id'] for r in rows])
        self.assertEqual(moved[2]['start_line'],5)

    def test_fences_setext_crlf_and_markdown_hash_trimming(self):
        text='Title\r\n=====\r\n```python\r\n# fake\r\n```\r\n---\r\n\r\n## Real ###\r\n~~~\r\n## fake2\r\n~~~\r\n'
        self.assertEqual([r['title'] for r in sections.parse(text)], ['Title','Real'])
        self.assertEqual(sections.parse('##not-heading\n')[0]['id'], 'preamble')

    def test_empty_and_no_heading_documents(self):
        self.assertEqual(sections.parse(''), [])
        self.assertEqual(sections.parse('a\nb\n')[0]['end_line'],2)
        self.assertEqual(sections.parse('# Last')[0]['end_line'],1)

    def test_duplicate_headings_branches_explicit_anchors_and_unicode(self):
        rows=sections.parse('# A\n## Shared\n## Shared\n# B\n## Shared\n## Правила {#rules}\n')
        self.assertEqual([r['id'] for r in rows], ['a','a/shared','a/shared~2','b','b/shared','b/rules'])
        self.assertEqual(sections.slug('Навигация'), 'навигация')
        self.assertLessEqual(len(sections.slug('A'*1000)),32)

    def test_literal_full_paths_unique_names_directories_and_ambiguous_names(self):
        paths=['src/rules.py','ui/view.js','a/shared.py','b/shared.py']
        links, ambiguity=sections.associations('`rules.py` [UI](ui/view.js) `a/` shared.py nonexistent.py',paths)
        self.assertEqual(links,['a/shared.py','src/rules.py','ui/view.js'])
        self.assertEqual(ambiguity,['shared.py'])
        self.assertEqual(sections.associations('not_src/rules.py',paths)[0],[])

    def test_index_contains_vocabulary_and_literal_search_without_bodies(self):
        data=fixture('# Architecture\n## Rules\nUse src/rules.py for deterministic moves.\n## UI\nui/view.js renders.\n')
        index=sections.build(data, counter=len)
        text=sections.artifact(index)
        for term in ['Game.move','Game','BOARD_SIZE','typing','drawBoard','architecture/rules','src/rules.py']:
            self.assertIn(term,text)
        hits=sections.search(index,'Game.move')
        self.assertTrue(any(r.get('id')=='architecture/rules' for r in hits['matches']))
        self.assertEqual(sections.search(index,'$(touch X)')['total'],0)
        self.assertNotIn('return ',text)

    def test_map_is_much_shorter_than_detailed_decisions(self):
        data=fixture('# Architecture\n## Rules\nsrc/rules.py\n'+('Pure deterministic domain behavior and rationale.\n'*600))
        index=sections.build(data,counter=len)
        self.assertLess(len(sections.artifact(index)),len(data['architecture']['text'])//10)
        page=architecture_map.navigation(data,limit=1)
        self.assertNotIn('Pure deterministic domain behavior and rationale.',page)
        self.assertIn('Game',sections.artifact(index))

    def test_page_is_byte_bounded_and_reconstructs_one_long_unicode_line(self):
        data=fixture('# Unicode\n'+('界😀'*3000))
        sha=data['architecture']['sha256']; offset=0; chunks=[]
        while True:
            page=sections.page(data,'unicode',sha,offset,max_bytes=257)
            self.assertLessEqual(len(page['text'].encode()),257)
            self.assertGreater(page['next_offset'],offset)
            chunks.append(page['text']);offset=page['next_offset']
            if not page['more']: break
        self.assertEqual(''.join(chunks),data['architecture']['text'])

    def test_stale_unknown_duplicate_and_invalid_offsets_fail_explicitly(self):
        data=fixture('# Rules\nDetails\n'); sha=data['architecture']['sha256']
        for ids, expected in [(['rules'],'0'*64), (['missing'],sha), (['rules','rules'],sha)]:
            with self.assertRaises(ValueError):sections.selected(data,ids,expected)
        for offset in [-1,1000]:
            with self.assertRaises(ValueError):sections.page(data,'rules',sha,offset)
        changed=copy.deepcopy(data);changed['architecture']['sha256']='1'*64
        with self.assertRaisesRegex(ValueError,'changed'):sections.page(changed,'rules',sha)

    def test_search_pagination_preserves_every_match(self):
        index=sections.build(fixture('# Rules\nsrc/rules.py\n## Child\nGame logic\n'),counter=len)
        first=sections.search(index,'rules',limit=1)
        all_rows=[];offset=0
        while True:
            page=sections.search(index,'rules',offset,1);all_rows+=page['matches'];offset=page['next_offset']
            if not page['more']:break
        self.assertEqual(len(all_rows),first['total'])
        self.assertEqual(len({json.dumps(r,sort_keys=True) for r in all_rows}),len(all_rows))
        with self.assertRaises(ValueError):sections.search(index,'')

    def test_generated_map_corruption_and_line_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'project';root.mkdir();out=Path(folder)/'shadow'
            (root/'rules.py').write_text('def move():\n    """Advance a move."""\n    return 1\n')
            doc=root/'architecture.md';doc.write_text('# Rules\nrules.py\n')
            data=scan(root,['.']);write_map(data,out)
            frozen={'shadow':str(out)}
            self.assertEqual(shadow.verify(frozen,data),[])
            for name in ['architecture-map.md','architecture-map.json']:
                with self.subTest(name=name):
                    (out/name).write_text('{}')
                    self.assertTrue(shadow.verify(frozen,data));write_map(data,out)
            doc.write_text('Intro\n'+doc.read_text())
            after=scan(root,['.']);self.assertTrue(shadow.verify(frozen,after))
            write_map(after,out);index=json.loads((out/'architecture-map.json').read_text())
            self.assertEqual(index['sections'][1]['start_line'],2)
            self.assertEqual(shadow.verify(frozen,after),[])

    def test_symbol_mentions_link_unique_owners_without_guessing_ambiguous_symbols(self):
        data=fixture('# Rules\nUse Game.move for deterministic changes.\n')
        index=sections.build(data,counter=len)
        self.assertEqual(index['sections'][0]['files'], ['src/rules.py'])
        data['files'][1]['symbols'].append({'kind':'function','name':'Game.move'})
        index=sections.build(data,counter=len)
        self.assertEqual(index['sections'][0]['files'], [])
        self.assertEqual(index['sections'][0]['ambiguous_symbols'], ['Game.move'])

    def test_literal_search_exposes_exact_match_beyond_representative_names(self):
        data=fixture('# Rules\nsrc/rules.py\n')
        data['files'][0]['symbols']=[{'kind':'function','name':'method_'+str(i)} for i in range(100)]
        index=sections.build(data,counter=len)
        self.assertNotIn('method_99',sections.artifact(index))
        file_row=next(r for r in sections.search(index,'method_99')['matches'] if r['kind']=='file')
        self.assertIn('method_99',file_row['functions'])
