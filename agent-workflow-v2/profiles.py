"""Resolve private Pi profiles and bounded budgets for one selected todo."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRESETS = {
    'small': {'input_tokens': 16384, 'output_tokens': 8192, 'reasoning_budget': 2048},
    'standard': {'input_tokens': 24576, 'output_tokens': 16384, 'reasoning_budget': 4096},
    'large': {'input_tokens': 40960, 'output_tokens': 32768, 'reasoning_budget': 8192},
}
MAX_TASK_INPUT = 57344
CEILINGS = {name:98304 for name in ('quality','speed','gemma')}
CEILINGS.update({'27b':98304, 'flash':131072})
WINDOWS = [32768, 65536, 98304, 131072]


def load(name: str) -> dict:
    """Read an installed named profile without allowing arbitrary path traversal."""
    path = BASE / 'profiles' / (name + '.json')
    if path.parent != BASE / 'profiles' or not path.is_file():
        raise ValueError(f'Unknown profile {name!r}; use --list-profiles')
    data = json.loads(path.read_text())
    data['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return data


def catalog() -> dict:
    """List reusable planner/executor combinations and their task presets."""
    return {'profiles': {p.stem: load(p.stem) for p in sorted((BASE / 'profiles').glob('*.json'))},
            'task_presets': PRESETS}


def apply_identity(args) -> dict:
    """Choose providers before selecting a task; explicit CLI choices take precedence."""
    profile = load(args.profile) if getattr(args, 'profile', None) else {}
    for key, default in [('model', '27b'), ('planner', 'local'), ('executor', 'local'),
                         ('planner_model', None)]:
        if getattr(args, key, None) is None:
            setattr(args, key, profile.get(key, default))
    return profile


def resolve(args, task: dict, profile: dict) -> dict:
    """Merge CLI, task recipe, preset and role defaults without expanding retrieval scope."""
    role = profile.get(args.role, {})
    recipe = task.get('context', {})
    size = getattr(args, 'task_size', None) or recipe.get('preset') or role.get('preset')
    preset = PRESETS[size] if size else {}
    forced = getattr(args, 'task_size', None) is not None
    cloud = args.planner == 'chatgpt' if args.role in ('architect','research','intake','reviewer','memory') else args.executor == 'chatgpt'
    from planning_limits import CLOUD_WINDOW,CLOUD_INPUT
    context = getattr(args, 'context', None) or recipe.get('window_tokens') or (CLOUD_WINDOW if cloud else profile.get('context',65536))
    if cloud and args.role in ('architect','reviewer'):
        role={**role,'input_tokens':CLOUD_INPUT,'output_tokens':32768}
    output_default = 8192 if context <= 32768 else 32768

    def value(cli, field, key, default):
        explicit = getattr(args, cli, None)
        if explicit is not None:
            return explicit
        if forced and key in preset:
            return preset[key]
        return recipe.get(field, preset.get(key, role.get(key, default)))

    output = value('output_tokens', 'max_output_tokens', 'output_tokens', output_default)
    result = {'context': context, 'output_tokens': output,
              'input_tokens': value('input_tokens', 'max_input_tokens', 'input_tokens', context-output-8192),
              'thinking': value('thinking', 'thinking', 'thinking', 'off'),
              'reasoning': value('reasoning', 'reasoning_effort', 'reasoning', 'xhigh' if args.role == 'architect' else 'medium'),
              'reasoning_budget': value('reasoning_budget', 'reasoning_budget_tokens', 'reasoning_budget',
                                        profile.get('backend_controls', {}).get('budget') if args.model=='quality' else None),
              'stop_after_pass': getattr(args, 'stop_after_pass', None), 'task_preset': size,
              'profile': profile.get('name'), 'profile_sha256': profile.get('sha256')}
    # Task presets retain the selected backend's cap unless explicitly overridden.
    if (not forced and getattr(args, 'reasoning_budget', None) is None
            and 'reasoning_budget_tokens' not in recipe and 'reasoning_budget' in role):
        result['reasoning_budget'] = role['reasoning_budget']
    result['sampling'] = profile.get('sampling', {})
    if result['stop_after_pass'] is None:
        result['stop_after_pass'] = role.get('stop_after_pass', False)
    if getattr(args,'uncapped_thinking',False):
        if getattr(args,'reasoning_budget',None) is not None:
            raise ValueError('Choose a thinking cap or --uncapped-thinking')
        result['reasoning_budget'] = None
    cloud = args.planner == 'chatgpt' if args.role in ('architect', 'research', 'intake','reviewer','memory') else args.executor == 'chatgpt'
    if (not cloud and not forced and args.model == 'quality' and result['thinking'] == 'on' and
            getattr(args, 'project', None) and getattr(args, 'reasoning_budget', None) is None and
            'reasoning_budget_tokens' not in recipe and not getattr(args, 'uncapped_thinking', False)):
        from thinking_caps import load as default_cap
        saved = default_cap(args.project)
        if saved is not None:
            result['reasoning_budget'] = min(saved, output - 2048)
    if cloud or result['thinking'] == 'off' or args.model == 'gemma':
        if getattr(args, 'reasoning_budget', None) is not None:
            raise ValueError('Separate thinking caps require a local Qwen thinking-on role')
        result['reasoning_budget'] = None
    validate(result, args.model, cloud)
    return result


def validate(config: dict, model: str, cloud=False) -> None:
    """Reject impossible windows, output reserves and budgets before launching a session."""
    from planning_limits import CLOUD_WINDOW,CLOUD_MODEL_OUTPUT
    if (cloud and (type(config['context']) is not int or not 32768<=config['context']<=CLOUD_WINDOW)) or (not cloud and (config['context'] not in WINDOWS or config['context'] > CEILINGS[model])):
        raise ValueError(f'Invalid {model} workflow context; ceiling {CEILINGS[model]}')
    for key in ['input_tokens', 'output_tokens']:
        number = config[key]
        maximum=(CLOUD_MODEL_OUTPUT if key=='output_tokens' else CLOUD_WINDOW) if cloud else (32768 if key=='output_tokens' else 131072)
        if type(number) is not int or not 512 <= number <= maximum:
            raise ValueError(f'Invalid {key} budget')
    if config['input_tokens'] + config['output_tokens'] + 8192 > config['context']:
        raise ValueError('Input + output + 8192 template reserve exceeds the task context; split the task')
    if config['thinking'] not in ['on', 'off'] or config['reasoning'] not in ['low', 'medium', 'xhigh']:
        raise ValueError('Invalid thinking or reasoning setting')
    budget = config['reasoning_budget']
    if budget is not None and (type(budget) is not int or not 0 <= budget <= config['output_tokens']-2048):
        raise ValueError('Thinking cap must leave at least 2048 output tokens for edits/tool calls')
    if cloud and config['stop_after_pass']:
        raise ValueError('Automatic stop-after-pass currently supports local executors only')
