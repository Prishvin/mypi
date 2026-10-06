"""Verify final review evidence, follow-up scope and unchanged-run reuse."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import test_plan_runner as fixture_helpers
from plan_runner import execute
from review_packet import build, test_names
from review_store import validate
from role_selection import load, select
from planner import prepare_catalog
import plans


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_helpers.RunnerTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.save()
        f=self.fixture;execute(f.root,f.path,f.folder,f.fake)
        self.packet=build(f.root,f.path,f.folder)
        self.followup=f.base/'followup.json'

    def test_packet_contains_results_and_contracts_without_implementation(self):
        raw=json.dumps(self.packet)
        self.assertNotIn('return text.lower()',raw)
        self.assertIn('task:T1',self.packet['evidence_ids'])
        self.assertEqual(self.packet['tasks'][0]['evidence'][0]['exit_code'],0)
        self.assertEqual(len(self.packet['completed_contracts']),1)
        self.fixture.source.write_text(self.fixture.source.read_text()+'# later edit\n')
        with self.assertRaisesRegex(ValueError,'unchanged completed'):
            build(self.fixture.root,self.fixture.path,self.fixture.folder)

    def test_browser_json_checks_reach_reviewer_without_unrelated_log_fields(self):
        log=self.fixture.base/'browser.log'
        log.write_text(json.dumps({'passed':True,'checks':['keyboard activation works','reset restores input'],
                                   'source':'PRIVATE IMPLEMENTATION'}))
        self.assertEqual(test_names(log),['PASS: keyboard activation works','PASS: reset restores input'])

    def test_clean_review_needs_no_invented_followup(self):
        result=validate({'verdict':'clean','summary':'No supported gap in supplied evidence.','findings':[]},self.packet,self.followup)
        self.assertIsNone(result['followup_plan'])
        with self.assertRaisesRegex(ValueError,'followup needs findings'):
            validate({'verdict':'followup','summary':'Nothing','findings':[]},self.packet,self.followup)

    def test_findings_need_real_evidence_and_cover_every_granular_todo(self):
        task=fixture_helpers.todo('R1','test_more.py'); task['tests']=[['python3','-m','unittest','test_more']]
        task['context']['interfaces']=[]
        plans.save(self.fixture.root,['.'],{'plan_version':3,'goal':'Add boundary checks','architecture':'Pure test seam','tasks':[task]},self.followup)
        data={'verdict':'followup','summary':'Add boundary coverage','findings':[{'kind':'unit-test-gap',
              'observation':'Empty input is absent from the supplied acceptance contract.', 'evidence':['task:T1'],'tasks':['R1']}]}
        self.assertEqual(validate(data,self.packet,self.followup)['followup_plan'],str(self.followup))
        bad=copy.deepcopy(data);bad['findings'][0]['evidence']=['invented-error']
        with self.assertRaisesRegex(ValueError,'real packet evidence'):validate(bad,self.packet,self.followup)
        bad=copy.deepcopy(data);bad['findings'][0]['tasks']=[]
        with self.assertRaisesRegex(ValueError,'real packet evidence'):validate(bad,self.packet,self.followup)

    def test_independent_selections_live_outside_project(self):
        base=self.fixture.base/'toolkit'
        selected=select(self.fixture.root,'planner','local',base)
        self.assertEqual(selected['planner'],'qwen');self.assertEqual(selected['reviewer'],'qwen')
        selected=select(self.fixture.root,'reviewer','local',base)
        self.assertEqual(selected['models']['reviewer']['reasoning'],'medium')
        selected=select(self.fixture.root,'planner','chatgpt',base)
        self.assertEqual(selected['models']['planner'],{'backend':'chatgpt','model':'gpt-6.1-sol','reasoning':'xhigh'})
        self.assertEqual(load(self.fixture.root,base)['reviewer'],'qwen')
        self.assertFalse((self.fixture.root/'project-settings').exists())

    def test_private_catalog_preserves_auth_and_maps_real_xhigh(self):
        folder=self.fixture.base/'config';folder.mkdir()
        (folder/'auth.json').write_text('private credential sentinel')
        prepare_catalog(folder,{'baseUrl':'http://127.0.0.1:8000/v1','models':[]})
        model=json.loads((folder/'models.json').read_text())['providers']['openai']['models'][0]
        self.assertEqual(model['id'],'gpt-6.1-sol');self.assertEqual(model['api'],'openai-responses')
        self.assertEqual(model['thinkingLevelMap']['xhigh'],'xhigh')
        self.assertIsNone(model['thinkingLevelMap']['minimal'])
        self.assertEqual((folder/'auth.json').read_text(),'private credential sentinel')


if __name__=='__main__':unittest.main()
