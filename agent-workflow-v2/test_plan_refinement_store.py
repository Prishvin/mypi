"""Prove typed refinement assembly, immutable staging and unchanged final gates."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from plan_draft import bind, restore, digest
from plan_refinement_store import stage, child_directory, assemble
from project_map import scan
from plans import save, require_review
from test_plan_runner import todo


class RefinementStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base/'project'; self.root.mkdir()
        self.task = todo('A'); self.task['tests'] = [['python3','-m','unittest']]; self.task['files'].append('architecture.md')
        self.plan = {'plan_version':3,'goal':'Normalize text','architecture':'Pure functions',
                     'planning_review':{'required':True,'status':'draft'},'tasks':[self.task]}
        self.source = self.base/'draft.json'; self.source.write_text(json.dumps(self.plan))
        self.bound = self.base/'bound.json'
        bind(self.root,self.source,self.bound,scan(self.root,['.'])['snapshot'],target='A')
        self.output = self.base/'published.json'

    def children(self):
        first = todo('A1'); first['tests'] = [['python3','-m','unittest']]; first['files'].append('architecture.md')
        second = copy.deepcopy(self.task); second['depends_on'] = ['A1']
        return [first,second]

    def receipts(self, children=None):
        return [stage(self.root,['.'],self.bound,t)['child_ref'] for t in children or self.children()]

    def publish(self, fields):
        proposal = restore(self.root,['.'],self.bound,fields)
        save(self.root,['.'],proposal,self.output)
        return json.loads(self.output.read_text())

    def test_flat_update_preserves_exact_values_and_untouched_contracts(self):
        fields = {'steps':['Inspect inputs','Test Unicode separators'], 'assumptions':['Input is text'],
                  'context_overlay':{'max_input_tokens':16000}}
        before = copy.deepcopy(fields)
        result = self.publish(fields)['tasks'][0]
        self.assertEqual(result['steps'],fields['steps']); self.assertEqual(fields,before)
        for key in ('acceptance','tests','coverage','files','goal'):
            self.assertEqual(result[key],self.task[key])
        self.assertEqual(result['context']['max_input_tokens'],16000)
        self.assertEqual(result['context']['estimate'],self.task['context']['estimate'])
        with self.assertRaisesRegex(ValueError,'refinement'):require_review(json.loads(self.output.read_text()))

    def test_unchanged_and_legacy_native_artifacts_remain_supported(self):
        for fields in ({'unchanged':True},{'task_updates':[{'id':'A'}]}):
            result = restore(self.root,['.'],self.bound,fields)
            self.assertEqual(result['tasks'],self.plan['tasks'])

    def test_unknown_mixed_empty_and_wrong_target_never_publish(self):
        for fields in ({},{'id':'B'},{'tasks':[]},{'unchanged':False},
                       {'unchanged':True,'steps':['a','b']},
                       {'child_refs':['a'*64,'b'*64],'steps':['a','b']},
                       {'task_updates':[{'id':'B'}]}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):self.publish(fields)
            self.assertFalse(self.output.exists())

    def test_staging_is_idempotent_versioned_and_does_not_publish_or_touch_source(self):
        child = self.children()[0]; original = copy.deepcopy(child)
        snapshot = scan(self.root,['.'])['snapshot']; pinned = self.bound.read_bytes()
        first = stage(self.root,['.'],self.bound,child)
        self.assertFalse(first['plan_accepted']); self.assertEqual(child,original)
        self.assertEqual(first,stage(self.root,['.'],self.bound,child))
        child['assumptions'] = ['ASCII fixture only']
        second = stage(self.root,['.'],self.bound,child)
        self.assertNotEqual(first['child_ref'],second['child_ref'])
        self.assertEqual(len(list(child_directory(self.bound).glob('*.json'))),2)
        self.assertFalse(self.output.exists()); self.assertEqual(pinned,self.bound.read_bytes())
        self.assertEqual(scan(self.root,['.'])['snapshot'],snapshot)

    def test_split_assembles_exact_children_and_validates_full_plan(self):
        children = self.children(); refs = self.receipts(children)
        fields = {'child_refs':refs,'architecture_replacements':[{'old':'Pure functions','new':'Pure modules'}]}
        result = self.publish(fields)
        self.assertEqual(result['architecture'],'Pure modules')
        self.assertEqual([t['id'] for t in result['tasks']],['A1','A'])
        for saved,authored in zip(result['tasks'],children):
            for key,value in authored.items():self.assertEqual(saved[key],value)

    def test_each_child_uses_same_v3_validation_as_final_plan(self):
        for mutate in (lambda t:t['context'].update(margin_tokens=1024),
                       lambda t:t.update(coverage=[]), lambda t:t.update(steps=['only']),
                       lambda t:t['execution'].update(timeout_seconds=99999),
                       lambda t:t.update(files=['../escape.py']),
                       lambda t:t.update(status='done'),lambda t:t.update(depends_on='A')):
            child = self.children()[0]; mutate(child)
            with self.subTest(child=child),self.assertRaises(ValueError):stage(self.root,['.'],self.bound,child)
        self.assertFalse(child_directory(self.bound).exists())

    def test_partial_reordered_missing_duplicate_or_traversing_receipts_rejected(self):
        refs = self.receipts()
        for invalid in (refs[:1],refs[::-1],[refs[0]]*2,[refs[0],'a'*64],['../../x',refs[1]]):
            with self.subTest(refs=invalid),self.assertRaises(ValueError):self.publish({'child_refs':invalid})
        self.assertFalse(self.output.exists())

    def test_final_preservation_failure_keeps_good_receipt_for_corrected_child(self):
        children = self.children(); children[-1]['files'] = ['other.py']
        children[0]['files'] = ['other.py']
        refs = self.receipts(children)
        with self.assertRaisesRegex(ValueError,'dropped'):self.publish({'child_refs':refs})
        fixed = stage(self.root,['.'],self.bound,self.children()[-1])['child_ref']
        result = self.publish({'child_refs':[refs[0],fixed]})
        self.assertEqual(result['tasks'][-1]['files'],self.task['files'])

    def test_bad_topology_and_uncovered_global_gaps_fail_final_gate(self):
        children = self.children(); children[-1]['depends_on'] = []
        with self.assertRaisesRegex(ValueError,'prerequisites'):self.publish({'child_refs':self.receipts(children)})
        bound = json.loads(self.bound.read_text())
        bound['proposal']['coverage_plan']={'gaps':[{'task':'A','case':{'id':'G','given':'x','when':'y','then':'z'},'test':['python3','-m','unittest']}]}
        bound['proposal_sha256']=digest(bound['proposal']);self.bound.write_text(json.dumps(bound))
        with self.assertRaises(ValueError):self.publish({'child_refs':self.receipts()})
        self.assertFalse(self.output.exists())

    def test_corrupt_and_cross_session_receipts_are_not_trusted(self):
        refs = self.receipts(); file = child_directory(self.bound)/(refs[0]+'.json')
        record = json.loads(file.read_text()); record['task']['goal']='Changed';file.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'corrupt'):self.publish({'child_refs':refs})
        self.assertFalse(self.output.exists())
        # Even an intact copied receipt cannot be replayed in another session.
        other = self.base/'other.json';other.write_bytes(self.bound.read_bytes())
        shutil.copytree(child_directory(self.bound),child_directory(other))
        with self.assertRaises(ValueError):restore(self.root,['.'],other,{'child_refs':refs[::-1]})

    def test_source_or_draft_change_invalidates_both_stage_and_commit(self):
        refs = self.receipts();(self.root/'new.py').write_text('x=1\n')
        for call in (lambda:stage(self.root,['.'],self.bound,self.task),lambda:self.publish({'child_refs':refs})):
            with self.assertRaisesRegex(ValueError,'stale'):call()
        (self.root/'new.py').unlink()
        raw=json.loads(self.bound.read_text());raw['proposal']['goal']='Changed';self.bound.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'hash'):stage(self.root,['.'],self.bound,self.task)

    def test_child_tool_cannot_be_used_for_generic_or_coverage_review(self):
        for fields in ({},{'coverage_review':True}):
            raw=json.loads(self.bound.read_text());raw.pop('refine_task',None);raw.update(fields)
            self.bound.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError,'selected task'):stage(self.root,['.'],self.bound,self.task)
