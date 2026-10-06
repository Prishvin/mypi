"""Source validation, brief publication, shadow freshness and explicit remembering."""
import json
import tempfile
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch
from research_briefs import save_source
from knowledge_sources import validate
from knowledge import publish, read_project, digest, cache_path
from knowledge_journal import recover
from knowledge_context import select
from research_service import cached
from project_map import scan
from remember import remember
import shadow


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        self.root=base/'project'; self.root.mkdir()
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        self.session=base/'session'; self.session.mkdir()
        self.base=base/'toolkit'; self.base.mkdir()
        self.shadow=base/'shadow'
        (self.root/'rules.py').write_text('def parse(x):\n    return "HIDDEN_IMPLEMENTATION"\n')

    def draft(self, name='SGF Go'):
        row=save_source(self.session/'research',{'url':'https://example.com/spec','text':'A move value is a point. Empty values denote a pass.', 'source_type':'web-page'})
        return validate(self.session,{'topics':[{'keyword':name,'why':'Parse Go game moves correctly',
            'findings':[{'artifact_id':row['artifact_id'],'claim':'Moves have point coordinates; an empty value is a pass.',
                         'evidence':'Empty values denote a pass.','confidence':'high'}],
            'implementation_artifacts':[row['artifact_id']]}]})

    def test_source_presence_is_enforced_and_quotes_cannot_be_invented(self):
        row=save_source(self.session/'research',{'url':'https://example.com/spec','text':'Actual source sentence.','source_type':'web-page'})
        topic={'keyword':'format','why':'Needed','findings':[{'artifact_id':row['artifact_id'],
               'claim':'A claim','evidence':'Invented sentence','confidence':'high'}]}
        with self.assertRaisesRegex(ValueError,'must occur'):
            validate(self.session,{'topics':[topic]})
        topic['findings'][0]['evidence']='Actual source sentence.'
        topic['implementation_artifacts']=['0'*16]
        with self.assertRaises((ValueError,OSError)):
            validate(self.session,{'topics':[topic]})

    def test_publish_preserves_manual_notes_and_merges_topics_with_cache(self):
        (self.root/'knowledge.md').write_text('# Notes\nUse small modules.\n')
        publish(self.root,self.draft(),'Request',read_project(self.root),self.base)
        text=(self.root/'knowledge.md').read_text()
        self.assertIn('Use small modules.',text); self.assertNotIn('HIDDEN_IMPLEMENTATION',text)
        self.assertTrue(cached(self.root,'Request',self.base))
        self.assertFalse(cached(self.root,'Another request',self.base))
        publish(self.root,self.draft('Another format'),'Another request',read_project(self.root),self.base)
        text=(self.root/'knowledge.md').read_text()
        self.assertIn('### SGF Go',text); self.assertIn('### Another format',text)
        selected=select(self.root,['SGF Go'])
        self.assertNotIn('Another format',selected)

    def test_concurrent_edits_and_managed_drift_are_rejected(self):
        expected=read_project(self.root)
        (self.root/'knowledge.md').write_text('Human changed this')
        with self.assertRaisesRegex(ValueError,'changed during'):
            publish(self.root,self.draft(),'Request',expected,self.base)
        publish(self.root,self.draft(),'Request',read_project(self.root),self.base)
        path=self.root/'knowledge.md'
        path.write_text(path.read_text().replace('Empty','Incorrect'))
        # Alter the managed claim, not the external raw evidence.
        path.write_text(path.read_text().replace('empty value','nonempty value'))
        with self.assertRaisesRegex(ValueError,'Managed knowledge changed'):
            publish(self.root,self.draft(),'Request',read_project(self.root),self.base)

    def test_journal_recovers_only_matching_document_and_cache_expires(self):
        publish(self.root,self.draft(),'Request',read_project(self.root),self.base)
        cache=cache_path(self.root,self.base); state=json.loads(cache.read_text())
        pending=cache.with_name('pending.json'); pending.write_text(json.dumps(state)); cache.unlink()
        recover(self.root,cache,digest)
        self.assertTrue(cache.exists()); self.assertFalse(pending.exists())
        self.assertFalse(cached(self.root,'Request',self.base,state['created_epoch']+8*86400))
        pending.write_text(json.dumps({**state,'knowledge_sha256':'wrong'})); cache.unlink()
        recover(self.root,cache,digest); self.assertFalse(cache.exists())

    def test_forced_refresh_uses_fresh_phase_instead_of_replaying_old_draft(self):
        from research_service import research
        folder=self.base/'research';folder.mkdir()
        (folder/'phase-result.json').write_text('{"passed":true}')
        with patch('research_service.run',return_value=({'passed':False},None)) as run:
            research(self.root,'Request',folder,refresh=True,base=self.base)
            self.assertEqual(run.call_args.args[3],folder/'pass-1')

    def test_research_frames_development_request_as_data_not_a_plan_command(self):
        """A plan_store request cannot redefine the separate research phase."""
        from research_service import research
        request = 'Build the game and save a granular plan with plan_store.'
        with patch('research_service.run',return_value=({'passed':False},None)) as run:
            research(self.root,request,self.base/'fresh-research',base=self.base)
        prompt = run.call_args.args[2]
        self.assertTrue(prompt.startswith('RESEARCH PHASE ONLY.'))
        payload = json.loads(prompt.split('\n\n',1)[1])
        self.assertEqual(payload['task'], request)
        self.assertIn('Do not design', prompt.split('\n\n',1)[0])

    def test_knowledge_changes_snapshot_scope_and_shadow_without_source_bodies(self):
        before=scan(self.root,['.'])
        publish(self.root,self.draft(),'Request',read_project(self.root),self.base)
        after=scan(self.root,['.']); self.assertNotEqual(before['snapshot'],after['snapshot'])
        from policy import validate_change
        self.assertFalse(validate_change(before,after,['rules.py'])['passed'])
        self.assertTrue(validate_change(before,after,['rules.py','knowledge.md'])['passed'])
        shadow.refresh(self.root,['.'],self.shadow)
        self.assertEqual((self.shadow/'knowledge.md').read_text(),(self.root/'knowledge.md').read_text())
        self.assertNotIn('HIDDEN_IMPLEMENTATION',(self.shadow/'architecture.md').read_text())
        (self.shadow/'knowledge.md').write_text('stale')
        self.assertTrue(shadow.verify({'shadow':str(self.shadow)},after))

    def test_remember_saves_distilled_essentials_and_refreshes_shadow(self):
        response='Several explanations. Chosen architecture: pure SGF parser, separate browser renderer.'
        calls=[]
        def phase(root,role,request,folder,backend,timeout):
            calls.append((role,json.loads(request)))
            return {'passed':True},{'items':[{'text':'Keep the SGF parser separate from browser rendering.',
                'evidence':'pure SGF parser, separate browser renderer.'}]}
        result=remember(self.root,response,self.session,self.shadow,self.base,phase_fn=phase)
        text=(self.root/'knowledge.md').read_text()
        self.assertIn('Keep the SGF parser',text);self.assertNotIn('Several explanations',text)
        self.assertNotIn('Full saved output',text)
        self.assertEqual(text,(self.shadow/'knowledge.md').read_text())
        self.assertTrue(result['distilled'])
        self.assertTrue(remember(self.root,response,self.session,self.shadow,self.base,phase_fn=phase)['duplicate'])
        self.assertEqual(len(calls),2)  # Each command still makes a fresh request.
        self.assertEqual(calls[0][0],'memory')

    def test_full_knowledge_is_not_evicted_for_distillation(self):
        path=self.root/'knowledge.md';path.write_text('x'*7900);before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'full'):
            remember(self.root,'A long saved response',self.session,self.shadow,self.base,phase_fn=lambda *a:None)
        self.assertEqual(path.read_bytes(),before)


if __name__=='__main__': unittest.main()
