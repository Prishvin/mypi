"""Prepare genuine private Pi RPC sessions with the terminal workflow's controls."""
import json
from pathlib import Path
from types import SimpleNamespace
from config import FLOW
import launch
import role_selection
import thinking_caps


def prepare(row,folder,role='chat'):
    cfg=row['settings']; project=Path(row['project'])
    for key in ('planner','reviewer'):role_selection.select(project,key,cfg[key])
    thinking_caps.select(project,cfg['thinking_cap'])
    cloud=role=='architect' and cfg['planner']=='chatgpt'
    args=SimpleNamespace(profile='chatgpt-quality' if cloud else 'mtplx-quality',project=project,
        role=role,context=98304,input_tokens=cfg['input_tokens'],output_tokens=cfg['output_tokens'],
        thinking=cfg['thinking'],reasoning='xhigh' if cloud else cfg['reasoning'],
        reasoning_budget=None if cloud or cfg['thinking']=='off' else cfg['thinking_cap'],
        model=None,planner=None,executor=None,planner_model=None,task_size=None,task=None,
        plan=None,todo=None,briefs=None,prefix=[],phase_output=None,review_packet=None,
        stop_after_pass=False,uncapped_thinking=False,prompt=None,json=False,interactive=True,
        batch=False,initial_stages=role=='architect',progress_seconds=30,timeout_seconds=1800)
    prepared=launch.prepare(args)
    folder.mkdir(parents=True,exist_ok=True)
    prepared['command']+=['--mode','rpc','--session',str(folder/'history.jsonl')]
    (folder/'launch.json').write_text(json.dumps(prepared,indent=2))
    return prepared


def restore(folder):
    return json.loads((folder/'launch.json').read_text())
