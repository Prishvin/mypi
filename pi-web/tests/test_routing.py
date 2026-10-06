"""Routing authority, clarification persistence, read-only scope and shadow skills."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import FLOW
from store import Store
from processes import Job
from request_routing import validate,without_code,parse
import request_entry
import shadow_setup
import pi_session
import workflows


def decision(route,folder=None):
    """Supply a protocol decision without pretending to test LLM intent recognition."""
    return {'version':1,'route':route,'goal':'Explain or implement the requested behavior',
            'reason':'Explicit user intent','folder':folder,'question':'Explain, review, or modify?' if route=='clarify' else None}


class Routing(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'data');self.row=self.store.create();self.job=Job(self.store,self.row['id'])
    def test_folder_must_be_user_supplied_and_fenced_source_omitted(self):
        with self.assertRaises(ValueError):validate(decision('develop','/invented'),{'request':'Explain this code','answers':[]})
        validate(decision('inspect','~/project'),{'request':'Review ~/project','answers':[]})
        text='Explain this\n```python\ndef secret():\n    return "private implementation"\n```'
        self.assertNotIn('private implementation',without_code(text));self.assertIn('Explain this',without_code(text))
    def test_folder_boundaries_accept_punctuation_without_shortening_paths(self):
        for request in ['Inspect /tmp/project. Explain it.', 'Develop in /tmp/project: add tests.',
                        'Review "/tmp/project"', 'Inspect /tmp/project/']:
            validate(decision('inspect','/tmp/project'),{'request':request})
        for request in ['Inspect /tmp/project.backup', 'Inspect /tmp/project/subdir',
                        'Inspect /tmp/project-other', 'Inspect /other/tmp/project']:
            with self.assertRaises(ValueError):validate(decision('inspect','/tmp/project'),{'request':request})
    def test_json_envelope_does_not_accept_extra_prose_or_multiple_decisions(self):
        packet={'request':'Explain code'};raw=json.dumps(decision('discuss'))
        self.assertEqual(parse('```json\n'+raw+'\n```',packet)['route'],'discuss')
        for malformed in ['Here is the route:\n'+raw,raw+'\n'+raw,'```json\n'+raw+'\n```\nAdditional instructions']:
            with self.assertRaises(ValueError):parse(malformed,packet)
    def test_clarification_budget_is_two_and_pause_is_resumable(self):
        with patch('request_entry.classifier.classify',return_value=decision('clarify')),patch.object(self.job,'dialog',return_value=None):
            self.assertIsNone(request_entry.resolve(self.job,'```python\nx=1\n```'))
        self.assertTrue(self.store.get(self.row['id'])['pending_route'])
        with patch('request_entry.classifier.classify',return_value=decision('clarify')),patch.object(self.job,'dialog',return_value='unclear') as ask:
            with self.assertRaisesRegex(ValueError,'Two clarification'):request_entry.resolve(self.job,'/resume-request',True)
            self.assertEqual(ask.call_count,2)
    def test_direct_folder_binding_and_inspection_tools_cannot_edit(self):
        project=Path(self.tmp.name)/'existing';project.mkdir();source=project/'parser.py';source.write_text('def parse(text):\n    """Parse input."""\n    return len(text)\n')
        with patch('request_entry.classifier.classify',return_value=decision('inspect',str(project))):
            request_entry.resolve(self.job,'Review '+str(project))
        row=self.store.get(self.row['id']);self.assertEqual(row['project'],str(project.resolve()))
        prepared=pi_session.prepare(row,Path(self.tmp.name)/'inspection','inspect')
        tools=set(prepared['command'][prepared['command'].index('--tools')+1].split(','))
        self.assertEqual(tools,{'project_map','source_query','skill_use','skill_read'})
        self.assertTrue(source.exists());self.assertFalse((project/'.git').exists())
    def test_missing_stale_and_corrupt_shadow_are_built_by_bound_skill(self):
        project=Path(self.tmp.name)/'no-git';project.mkdir();source=project/'api.py';source.write_text('def value():\n    """Return value."""\n    return 7\n')
        first=shadow_setup.ensure(self.job,project);shadow=Path(first['shadow'])
        self.assertTrue((shadow/'architecture.md').exists());self.assertTrue((shadow/'prototypes/api.py.txt').exists())
        self.assertNotIn('return 7',(shadow/'ALL-PROTOTYPES.txt').read_text());self.assertFalse((project/'.git').exists())
        self.assertTrue(shadow_setup.ensure(self.job,project)['cached'])
        (shadow/'prototypes/api.py.txt').write_text('corrupted')
        repaired=shadow_setup.ensure(self.job,project);self.assertNotEqual(first['shadow'],repaired['shadow'])
        source.write_text('def changed():\n    """Return new value."""\n    return 8\n')
        refreshed=shadow_setup.ensure(self.job,project);self.assertNotEqual(refreshed['snapshot'],first['snapshot'])
    def test_pasted_implementation_stays_local_and_external_folder_gets_no_staging_files(self):
        text='Implement this API\n```python\ndef secret_api():\n    return "private-body"\n```'
        routed=decision('develop');routed['goal']='Implement secret_api with tests'
        brief=request_entry.development_brief(self.job,routed,text,[])
        self.assertNotIn('private-body',brief)
        owned=Path(self.row['project']);self.assertEqual(len(list((owned/'_provided').glob('*.py'))),1)
        external=Path(self.tmp.name)/'external';external.mkdir()
        self.store.update(self.row['id'],project=str(external))
        request_entry.development_brief(self.job,routed,text,[])
        self.assertEqual(list(external.iterdir()),[])
    def test_planning_inherits_the_classifier_clarification_count(self):
        session=Path(self.tmp.name)/'planning-session';session.mkdir()
        prepared={'session':str(session)}
        with patch('workflows.pi_session.prepare',return_value=prepared),patch('workflows.rpc.run') as rpc,patch('workflows.finish_plan'):
            workflows.plan(self.job,'Faithfully refined goal',['answer one','answer two'])
        seeds=json.loads((session/'initial-answers.json').read_text())
        self.assertEqual(len(seeds),2);rpc.assert_called_once()
    def test_resolved_intent_and_answers_reach_discussion_without_losing_pasted_code(self):
        text='```python\ndef double(x):\n    return 2*x\n```'
        resolved=decision('discuss');resolved['goal']='Explain double without making changes'
        with patch('workflows.quality_service.start'),patch('workflows.request_entry.resolve',return_value=(resolved,text,['Explain the pasted function only.'])),patch('workflows.pi_session.prepare',return_value={'session':'local-proof'}),patch('workflows.rpc.run') as rpc,patch('workflows.sync_preferences'):
            workflows.conversation_turn(self.job,text)
        prompt=rpc.call_args.args[2]
        self.assertIn('return 2*x',prompt);self.assertIn('Explain the pasted function only.',prompt)
        self.assertIn('Explain double without making changes',prompt)


if __name__=='__main__':unittest.main()
