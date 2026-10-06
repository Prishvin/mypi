"""Private local web application paths and validated per-conversation settings."""
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
FLOW = ROOT/'agent-workflow-v2'
PYTHON = FLOW/'.venv/bin/python'
sys.path[:0] = [str(FLOW), str(ROOT)]
DEFAULTS = {'mode':'pi', 'planner':'qwen', 'reviewer':'qwen', 'input_tokens':24576,
            'output_tokens':8192, 'thinking_cap':2048, 'thinking':'on', 'reasoning':'medium'}


def settings(values, previous=None):
    """Reject unknown options and impossible budgets before starting a request."""
    if not isinstance(values,dict) or set(values)-set(DEFAULTS):
        raise ValueError('Unknown conversation settings')
    result={**(previous or DEFAULTS),**values}
    for key, allowed in {'mode':['pi','raw'], 'planner':['chatgpt','qwen'], 'reviewer':['chatgpt','qwen'],
                         'thinking':['on','off'], 'reasoning':['low','medium','xhigh']}.items():
        if result[key] not in allowed: raise ValueError('Invalid '+key)
    for key, low, high in [('input_tokens',4096,57344),('output_tokens',2048,32768),('thinking_cap',0,30720)]:
        if type(result[key]) is not int or not low<=result[key]<=high: raise ValueError('Invalid '+key)
    if result['input_tokens']+result['output_tokens']+8192>98304:
        raise ValueError('Input + output + template reserve must fit 96k')
    if result['thinking_cap']>result['output_tokens']-2048:
        raise ValueError('Thinking cap must leave 2048 tokens for the answer/tools')
    return result
