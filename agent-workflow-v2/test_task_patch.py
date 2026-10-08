"""Ensure failure reviews see the same cumulative patch debt as acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from task_patch import measure
from replan_brief import distill


class PatchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = {'before': {'root': str(self.root)}, 'declared_text': {}}

    def file(self, name, before, after):
        self.data['declared_text'][name] = before
        if after is not None:
            (self.root/name).write_text(after)

    def test_insertions_replacements_deletions_and_docs_are_counted(self):
        self.file('new.py', '', 'first\nsecond\n')
        self.file('edit.py', 'same\nold\n', 'same\nnew\n')
        self.file('gone.py', 'deleted\n', None)
        self.file('architecture.md', '# Original\n', '# Original\nNote\n')
        self.file('same.py', 'same\n', 'same\n')
        original = copy.deepcopy(self.data)
        result = measure(self.data)
        self.assertEqual(result['changed_lines'], 6)
        self.assertEqual(result['by_file'], {'new.py':2, 'edit.py':2, 'gone.py':1, 'architecture.md':1})
        self.assertEqual(result['over_limit_by'], 0)
        self.assertEqual(self.data, original)

    def test_retry_inherits_debt_instead_of_counting_only_its_increment(self):
        import tasks
        self.file('new.py', '', ''.join(f'line{i}\n' for i in range(305)))
        self.data.update(task={'files':['new.py']}, declared_hashes={'new.py':None})
        original = self.root/'original.json'; original.write_text(json.dumps(self.data))
        retry = self.root/'retry.json'
        retry.write_text(json.dumps({**self.data,'declared_text':{'new.py':(self.root/'new.py').read_text()}}))
        tasks.inherit_baseline(retry, original)
        result = measure(json.loads(retry.read_text()))
        self.assertEqual(result['changed_lines'], 305)
        self.assertEqual(result['over_limit_by'], 5)
        self.assertEqual(original.read_text(), json.dumps(self.data))
        (self.root/'new.py').write_text(''.join(f'line{i}\n' for i in range(299)))
        result = measure(json.loads(retry.read_text()))
        self.assertEqual(result['changed_lines'], 299)
        self.assertEqual(result['over_limit_by'], 0)

    def test_gate_uses_shared_measurement(self):
        import tasks
        self.file('new.py', '', 'value\n'*301)
        self.data.update(task={'files':['new.py'],'tests':[['test']]},declared_hashes={'new.py':None})
        state=self.root/'state.json'; state.write_text(json.dumps(self.data))
        with patch('tasks.current_snapshot',return_value=({'snapshot':'snapshot'}, {'new.py':'hash'}, 'snapshot')), \
             patch('tasks.validate_change',return_value={'changed':['new.py'],'violations':[]}), \
             patch('tasks.shadow.verify',return_value=[]), \
             patch('architecture_sync.verify',return_value=[]), \
             patch('task_progress.describe',return_value={}):
            gate=tasks.check(state)
        self.assertEqual(gate['patch_budget'],measure(self.data))
        self.assertEqual(gate['patch_lines'],301)
        self.assertIn('Patch has 301 changed lines; split into atomic tasks',gate['violations'])

    def test_focused_context_retains_counts_and_baseline_policy_without_source(self):
        self.file('new.py', '', 'private_implementation\n'*302)
        packet={'patch_budget':measure(self.data),'failed_todo':{'id':'T1'}}
        brief=distill(packet,focused=True)
        self.assertEqual(brief['patch_budget'],packet['patch_budget'])
        self.assertIn('original unfinished task baseline',brief['patch_budget']['baseline_policy'])
        self.assertNotIn('private_implementation',json.dumps(brief))


if __name__ == '__main__':
    unittest.main()
