"""Context trimming must preserve the selected contract and actual module relationships."""
import copy
import unittest
from revision_context import packet_data


def task(identifier, path, inputs=(), dependencies=()):
    """Create small contracts without application implementation."""
    return {'id': identifier, 'goal': identifier, 'files': [path, 'architecture.md'],
            'depends_on': list(dependencies), 'acceptance': [{'id': identifier+'-A', 'then': identifier}],
            'tests': [['node', identifier+'.test.mjs']], 'coverage': [],
            'context': {'interfaces': list(inputs)}, 'steps': ['PRIVATE_UNRELATED_STEPS']}


class RevisionContextTests(unittest.TestCase):
    def setUp(self):
        self.draft = {'goal': 'Project goal', 'architecture': 'Complete architecture', 'coverage_plan': {'requirements': []},
            'tasks': [task('producer','a.mjs'), task('selected','b.mjs',['a.mjs','shared.mjs']),
                      task('consumer','c.mjs',['b.mjs']), task('explicit','d.mjs',dependencies=['selected']),
                      task('unrelated','e.mjs',['shared.mjs'])]}

    def test_exact_selected_architecture_and_directional_contracts_are_preserved(self):
        before = copy.deepcopy(self.draft); data = packet_data('Request', self.draft, 'selected')
        self.assertEqual(data['current_task'], self.draft['tasks'][1])
        self.assertEqual(data['whole_plan']['architecture'], self.draft['architecture'])
        self.assertEqual([t['id'] for t in data['related_contracts']], ['producer','consumer','explicit'])
        self.assertEqual(len(data['whole_plan']['tasks']), 5)
        self.assertEqual(data['related_contracts'][0]['acceptance'], self.draft['tasks'][0]['acceptance'])
        self.assertEqual(self.draft, before)

    def test_shared_architecture_and_shared_helper_do_not_expand_to_every_task(self):
        data = packet_data('Request', self.draft, 'selected')
        self.assertNotIn('unrelated', [t['id'] for t in data['related_contracts']])
        for overview in data['whole_plan']['tasks']:
            self.assertNotIn('steps', overview); self.assertNotIn('acceptance', overview)
        for related in data['related_contracts']:
            self.assertNotIn('steps', related)

    def test_symbol_references_and_prerequisites_select_producers(self):
        self.draft['tasks'][1]['context'] = {'symbols':[{'path':'a.mjs','name':'parse'}]}
        self.draft['tasks'][1]['depends_on'] = ['unrelated']
        ids = [t['id'] for t in packet_data('Request', self.draft, 'selected')['related_contracts']]
        self.assertIn('producer', ids); self.assertIn('unrelated', ids)

    def test_missing_or_ambiguous_target_rejected(self):
        with self.assertRaises(ValueError): packet_data('Request', self.draft, 'missing')
        self.draft['tasks'].append(copy.deepcopy(self.draft['tasks'][1]))
        with self.assertRaises(ValueError): packet_data('Request', self.draft, 'selected')


if __name__ == '__main__': unittest.main()
