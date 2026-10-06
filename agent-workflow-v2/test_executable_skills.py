"""Execute real small pipelines and enforce boundaries independent of any project."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from skill_registry import BASE, load
from skill_runner import prepare, run, dispatch
from skill_process import execute
from research_search import search


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.session=Path(self.temp.name)/'session'; self.session.mkdir()

    def test_prepare_then_two_script_pipeline_and_literal_injection_text(self):
        with self.assertRaisesRegex(ValueError,'Prepare'):
            run(self.session,'text-metrics',{'text':'hello'},'research')
        contract=prepare(self.session,'text-metrics','research')
        self.assertIn('post_prompt',contract)
        text='hello\r\n$(touch /tmp/NEVER_EXECUTE_PI_TEST) `false`\r\n'
        result=run(self.session,'text-metrics',{'text':text},'research')
        self.assertEqual(len(result['steps']),2)
        self.assertEqual(result['data']['characters'],len(text.replace('\r\n','\n')))
        self.assertIsNone(result['data']['token_count'])
        self.assertTrue((Path(result['artifact_dir'])/'input.json').exists())
        with self.assertRaises(Exception):
            run(self.session,'text-metrics',{'text':'hello','unexpected':1},'research')

    def test_dispatch_matches_tool_name_and_roles(self):
        self.assertIn('purpose',dispatch(self.session,{'action':'prepare','name':'text-metrics'},'architect'))
        self.assertEqual(dispatch(self.session,{'action':'run','name':'text-metrics','inputs':{'text':'a b'}},'architect')['data']['words'],2)
        with self.assertRaises(ValueError):
            prepare(self.session,'text-metrics','intake')
        with self.assertRaises(ValueError):
            load('../planner-config')

    def test_prepared_version_change_and_symlink_pack_are_rejected(self):
        base=Path(self.temp.name)/'toolkit'
        shutil.copytree(BASE/'skills'/'text-metrics',base/'skills'/'text-metrics')
        prepare(self.session,'text-metrics','code',base)
        (base/'skills/text-metrics/SKILL.md').write_text('Changed instructions')
        with self.assertRaisesRegex(ValueError,'exact skill version'):
            run(self.session,'text-metrics',{'text':'abc'},'code',base)
        (base/'skills/text-metrics/linked-dir').symlink_to(BASE/'planner-config',target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlinks'):
            load('text-metrics',base)

    def test_process_timeout_and_hard_output_limit(self):
        with self.assertRaisesRegex(ValueError,'deadline'):
            execute([sys.executable,'-c','import time; time.sleep(5)'],self.session,.15,512,BASE)
        with self.assertRaisesRegex(ValueError,'byte limit'):
            execute([sys.executable,'-c','print("x"*10000)'],self.session,3,512,BASE)

    def test_duckduckgo_strict_failure_does_not_use_another_engine(self):
        with patch('research_search.get',side_effect=OSError('blocked')) as get:
            with self.assertRaisesRegex(ValueError,'duckduckgo: blocked'):
                search('SGF Go','duckduckgo',fallback=False)
        self.assertEqual(get.call_count,1)


if __name__=='__main__': unittest.main()
