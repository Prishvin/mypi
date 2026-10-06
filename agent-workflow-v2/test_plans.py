"""Verify granular handoffs, dependency order and planned acceptance coverage."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from plans import save, select, complete


def example_task(identifier='T1'):
    """Supply one bounded behavioral contract for tests and the demo plan."""
    return {'id': identifier, 'goal': 'Normalize slug separators', 'files': ['slug.py'],
            'acceptance': [{'id': 'A1', 'given': 'Repeated separators', 'when': 'slugify runs',
                            'then': 'One separator with no edge separator'}],
            'tests': [['python3', '-m', 'unittest']], 'coverage': [{'criterion': 'A1', 'test': 0}],
            'context': {'interfaces': ['slug.py'], 'symbols': [{'path': 'slug.py', 'name': 'slugify'}],
                        'reference_files': [], 'max_input_tokens': 6000, 'max_output_tokens': 4096}}


class PlanTests(unittest.TestCase):
    """Keep a plan actionable without passing the entire plan to an executor."""
    def setUp(self):
        """Create an isolated repository and external plan artifact."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'slug.py').write_text('def slugify(text):\n    """Make a slug."""\n    return text\n')
        self.output = Path(self.temp.name) / 'plan.json'
        self.plan = {'goal': 'Fix slugs', 'architecture': 'Pure function', 'tasks': [example_task()]}

    def test_uncovered_criterion_or_large_context_rejected(self):
        """Plans cannot omit coverage or ask for unlimited task context."""
        for mutate in [lambda t: t.update(coverage=[]),
                       lambda t: t['context'].update(max_input_tokens=128000)]:
            plan = copy.deepcopy(self.plan)
            mutate(plan['tasks'][0])
            with self.assertRaises(ValueError):
                save(self.root, ['.'], plan, self.output)

    def test_dependencies_and_completion_evidence(self):
        """Failed tasks stay pending; completed dependencies unlock the next todo."""
        second = example_task('T2')
        second['depends_on'] = ['T1']
        self.plan['tasks'].append(second)
        save(self.root, ['.'], self.plan, self.output)
        self.assertNotIn('architecture', select(self.output, 'T1'))
        with self.assertRaises(ValueError):
            select(self.output, 'T2')
        with self.assertRaises(ValueError):
            complete(self.output, 'T1', {'passed': False}, self.output.parent)
        complete(self.output, 'T1', {'passed': True, 'shadow_snapshot': 'verified'}, self.output.parent)
        self.assertEqual(select(self.output, 'T2')['id'], 'T2')
        self.assertEqual(json.loads(self.output.read_text())['tasks'][0]['status'], 'done')
