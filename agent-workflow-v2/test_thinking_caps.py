"""Test persisted defaults, explicit task precedence, and request isolation."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch
import profiles
import role_selection
import thinking_caps
from test_profiles import options

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'mtplx-pi-adapter'))
from pi_thinking_adapter import install


class ThinkingCapTests(unittest.TestCase):
    def test_preferences_and_task_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder); project=base/'project';project.mkdir()
            thinking_caps.select(project,8192,base)
            role_selection.select(project,'reviewer','local',base)
            self.assertEqual(thinking_caps.load(project,base),8192)
            args=options(profile='mtplx-quality',project=project)
            profile=profiles.apply_identity(args)
            with patch('thinking_caps.load',return_value=8192):
                self.assertEqual(profiles.resolve(args,{},profile)['reasoning_budget'],8192)
                task={'context':{'reasoning_budget_tokens':1024}}
                self.assertEqual(profiles.resolve(args,task,profile)['reasoning_budget'],1024)
                args.output_tokens=8192
                self.assertEqual(profiles.resolve(args,{},profile)['reasoning_budget'],6144)
                args.task_size='small'
                self.assertEqual(profiles.resolve(args,{},profile)['reasoning_budget'],2048)
                args.task_size=None
                args.uncapped_thinking=True
                self.assertIsNone(profiles.resolve(args,{},profile)['reasoning_budget'])
            thinking_caps.select(project,None,base)
            self.assertIsNone(thinking_caps.load(project,base))
            self.assertEqual(role_selection.load(project,base)['reviewer'],'qwen')
            for invalid in (-1,30721,True,'8192'):
                with self.assertRaises(ValueError):thinking_caps.select(project,invalid,base)

    def test_native_guard_replacement_is_request_local(self):
        @dataclass(frozen=True)
        class Config:
            enabled:bool=True
            budget_tokens:int=4096
        original=Config()
        class BadRequest(Exception):
            def __init__(self,**kwargs):super().__init__(kwargs)
        module=SimpleNamespace(_request_observability=lambda *a,**k:{'request_enable_thinking':True},
            _request_max_tokens=lambda r:r.output,_thinking_guard_config_for_request=lambda *a,**k:original,
            create_app=lambda state:None,HTTPException=BadRequest)
        install(module)
        request=SimpleNamespace(output=16384)
        def obs(value):return module._request_observability(request,metadata={'client':'pi','pi_thinking_cap':value})
        def guard(value):return module._thinking_guard_config_for_request(None,prompt_ids=[],request_observability=value)
        self.assertEqual(guard(obs(8192)).budget_tokens,8192)
        self.assertEqual(guard(obs(1024)).budget_tokens,1024)
        self.assertIs(guard({}),original)
        self.assertIsNone(guard(obs(0)))
        self.assertEqual(original.budget_tokens,4096)
        self.assertIs(guard({'request_enable_thinking':False,'pi_thinking_cap':8192}),original)
        for value in (-1,True,'8192',16384):
            with self.assertRaises(BadRequest):obs(value)


if __name__=='__main__':unittest.main()
