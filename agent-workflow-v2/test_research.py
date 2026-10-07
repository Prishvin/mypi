"""Validate public research, bounded excerpts and truthful brief provenance."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research_fetch import public_url, extract, fetch, PublicRedirects
from research_search import search
from research_briefs import save_source, distill, load_source, read_brief
from workflow_skills import instructions


class ResearchTests(unittest.TestCase):
    """Keep source fetching independent of the project and model executor."""
    def test_private_targets_and_redirects_rejected(self):
        """Research cannot call local generation APIs or follow a redirect to one."""
        for url in ['http://localhost:8080/','file:///tmp/a','https://user:pass@example.com/']:
            with self.assertRaises(ValueError):
                public_url(url)
        with patch('research_fetch.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',80))]):
            with self.assertRaises(ValueError):
                public_url('https://example.com')
        with self.assertRaises(ValueError):
            PublicRedirects().redirect_request(None,None,302,'',{},'http://localhost:8080/')

    def test_html_drops_scripts_and_preserves_readable_docs(self):
        """JavaScript and navigation are omitted from model-visible page excerpts."""
        text = extract('<nav>ignore</nav><script>bad()</script><p>API <b>contract</b>.</p><pre>sample()</pre>')
        self.assertNotIn('bad()',text)
        self.assertNotIn('ignore',text)
        self.assertIn('API contract.',text)

    def test_search_reports_engine_fallback(self):
        """A blocked Google result cannot be falsely reported as a Google success."""
        html = '<a href="https://example.com/docs">Official docs</a>'
        with patch('research_search.get',side_effect=[OSError('blocked'),(html,'https://duckduckgo.com','text/html')]):
            result = search('public API')
            self.assertEqual(result['used_engine'],'duckduckgo')
            self.assertIn('blocked',result['fallback_errors'][0])
            self.assertEqual(result['results'][0]['url'],'https://example.com/docs')

    def test_huggingface_and_stackoverflow_fetch_adapters(self):
        """Cards and answers carry their public-source type and useful metadata."""
        with patch('research_fetch.get',return_value=('Model card facts','https://cdn.example/card','text/plain')) as get:
            self.assertEqual(fetch('https://huggingface.co/org/model')['source_type'],'model-card')
            self.assertIn('/resolve/main/README.md',get.call_args.args[0])
        question = json.dumps({'items':[{'title':'Question','body':'<p>API usage</p>','score':3}]})
        answers = json.dumps({'items':[{'body':'<p>Answer</p>','score':5,'is_accepted':True}]})
        with patch('research_fetch.get',side_effect=[(question,'url','application/json'),(answers,'url','application/json')]):
            result = fetch('https://stackoverflow.com/questions/123/example')
            self.assertEqual(result['source_type'],'community-answer')
            self.assertIn('accepted=True',result['text'])

    def test_briefs_require_real_evidence_and_preserve_fetch_time(self):
        """Invented quotes and altered archives are rejected; selecting an excerpt is not a fresh fetch."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            row = save_source(root,{'url':'https://example.com/docs','text':'The input is immutable. Errors are explicit.',
                                    'source_type':'web-page','fetched_epoch':123})
            findings = [{'artifact_id':row['artifact_id'],'claim':'Treat the input as immutable',
                         'evidence':'The input is immutable.','confidence':'high'}]
            result = distill(root,'Choose API contract',findings,'Use a pure adapter',[])
            self.assertEqual(result['brief']['findings'][0]['fetched_epoch'],123)
            findings[0]['evidence'] = 'Made up evidence'
            with self.assertRaises(ValueError):
                distill(root,'Choose API',findings,'',[])
            path = Path(row['artifact']); data=json.loads(path.read_text()); data['text']='Changed'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_source(root,row['artifact_id'])

    def test_handoff_rejects_nonresearch_files(self):
        """A task recipe cannot read auth/config files as a research brief."""
        with self.assertRaises(ValueError):
            read_brief(Path(__file__).with_name('planner-config')/'auth.json')

    def test_noncontiguous_quote_names_finding_and_offers_exact_copy_recovery(self):
        """An actionable rejection never accepts stitched or quoted paraphrases."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            row = save_source(root, {'url':'https://example.com/docs',
                'text':'The event is dispatched to the document. Wait for a new click.',
                'source_type':'web-page'})
            valid = {'artifact_id':row['artifact_id'], 'claim':'Observe the event.',
                     'evidence':'event is dispatched', 'confidence':'high'}
            for quote in ('event; Wait for a new click', '"event is dispatched"',
                          'event is dispatched ... new click'):
                with self.assertRaisesRegex(ValueError, 'Finding 2, artifact '+row['artifact_id']):
                    distill(root, 'Events', [valid, {**valid, 'evidence':quote}], '', [])
            result = distill(root, 'Events', [valid, {**valid, 'evidence':'Wait for a new click.'}], '', [])
            self.assertEqual(len(result['brief']['findings']), 2)

    def test_quote_character_limit_is_distinct_from_missing_match(self):
        """Empty and oversized quotes get a precise length error before lookup."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            row = save_source(root, {'url':'https://example.com/docs', 'text':'x'*500,
                                    'source_type':'web-page'})
            for quote in ('', 'x'*401):
                with self.assertRaisesRegex(ValueError, 'Finding 1: evidence must contain 1-400'):
                    distill(root, 'Events', [{'artifact_id':row['artifact_id'], 'claim':'Fact',
                        'evidence':quote, 'confidence':'high'}], '', [])

    def test_private_brief_handoff_is_hash_bound(self):
        """A real saved brief is reusable by tasks; later text edits invalidate it."""
        sessions=Path(__file__).resolve().parent/'sessions'
        sessions.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=sessions) as directory:
            folder=Path(directory)/'research'
            row=save_source(folder,{'url':'https://example.com','text':'A pure input contract.', 'source_type':'web-page'})
            brief=distill(folder,'Contract',[{'artifact_id':row['artifact_id'],'claim':'Use pure inputs',
                          'evidence':'A pure input contract.','confidence':'high'}],'Inject dependencies',[])
            path=Path(brief['brief_path'])
            self.assertIn('Inject dependencies',read_brief(path))
            path.write_text(path.read_text().replace('Inject dependencies','Change dependencies'))
            with self.assertRaisesRegex(ValueError,'hash changed'):
                read_brief(path)

    def test_default_skills_are_active_and_bounded(self):
        """The explicit private loader enables research without global skill discovery."""
        text = instructions(Path(__file__).resolve().parent)
        for name in ['scoped-retrieval','task-finalize']:
            self.assertIn('ACTIVE PRIVATE PI SKILL: '+name,text)
        self.assertNotIn('ACTIVE PRIVATE PI SKILL: granular-planning',text)
        self.assertIn('duckduckgo-research',text)  # Available on demand, not removed.
        self.assertNotIn('Mouse displacement',text)  # Browser procedure is task-local.
        self.assertLess(len(text.encode()),14000)
