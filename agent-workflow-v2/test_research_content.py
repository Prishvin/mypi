"""Content extraction, context bounds and first-two-link failure behavior."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research_content import article,focus
from research_follow import research


class Content(unittest.TestCase):
    def test_main_article_excludes_sidebar_cookie_and_comments(self):
        body='<html><body><nav>BUY NOW</nav><aside>Subscribe to the newsletter</aside><div class="cookie-banner">Accept all cookies</div><main><article><h1>Drone ESC operation</h1>'+''.join('<p>An electronic speed controller switches six MOSFETs to commutate three motor phases. Timing uses back EMF feedback and PWM controls average voltage.</p>' for _ in range(3))+'</article></main><div id="comments">Unrelated comments</div><footer>All rights reserved</footer></body></html>'
        text,method=article(body)
        self.assertIn('six MOSFETs',text)
        for noise in ['BUY NOW','Subscribe','Accept all cookies','Unrelated comments','All rights reserved']:self.assertNotIn(noise,text)
        self.assertEqual(method,'trafilatura-main-content')
    def test_focus_finds_answer_far_beyond_first_page_and_bounds_unicode(self):
        text='\n'.join(['Irrelevant account and setup details.']*100+['The ESC commutates three motor phases by switching six MOSFETs.']+['Other manual information.']*100)
        result=focus(text,'ESC MOSFET commutation',512)
        self.assertIn('six MOSFETs',result['excerpt']);self.assertTrue(result['query_match']);self.assertTrue(result['truncated'])
        self.assertLessEqual(result['returned_bytes'],512)
        self.assertLessEqual(focus('電気回路 '*500,'電気回路',512)['returned_bytes'],512)
        self.assertFalse(focus('Ordinary article text without matches.','zzmissing')['query_match'])
    def test_first_two_only_and_blocked_first_does_not_hide_second(self):
        rows=[{'title':str(i),'url':'https://example.com/'+str(i)} for i in range(3)]
        def native(url):
            if url==rows[0]['url']:raise OSError('blocked')
            return {'url':url,'text':'An ESC controls motor commutation.','source_type':'web-page'}
        with tempfile.TemporaryDirectory() as tmp,patch('research_follow.search',return_value={'results':rows}) as search,patch('research_follow.fetch',side_effect=native) as fetch:
            result=research('drone ESC','motor commutation',Path(tmp))
            self.assertEqual(fetch.call_count,2);self.assertEqual(result['attempted_links'],2);self.assertEqual(result['read_links'],1)
            self.assertEqual([p['url'] for p in result['pages']],[r['url'] for r in rows[:2]])
            self.assertEqual(result['pages'][0]['status'],'unavailable');self.assertIn('artifact_id',result['pages'][1])
            self.assertFalse(search.call_args.kwargs['fallback'])


class Links(unittest.TestCase):
    def test_exact_topic_links_survive_without_tracking_or_script_targets(self):
        from research_content import links,relevant_links
        data=links('<nav><a href="/login">Account</a></nav><article><a href="sgf4.html">SGF game tree specification</a><a href="javascript:bad()">bad</a><a href="https://x.example/docs">Other topic</a></article>','https://example.com/sgf/')
        result=relevant_links(data,'SGF game tree syntax')
        self.assertEqual(result,[{'title':'SGF game tree specification','url':'https://example.com/sgf/sgf4.html'}])


if __name__=='__main__':unittest.main()
