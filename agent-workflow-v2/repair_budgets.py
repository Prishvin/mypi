"""Apply the user's minimum reasoning allowance to local Qwen repairs only."""
import json
from pathlib import Path

MIN_THINKING = 8192


def is_repair(args):
    """Recognize failure review and the selected corrective todo, not later tasks."""
    if args.role == 'architect':
        return bool(getattr(args, 'replan_evidence', None) or (
            getattr(args, 'plan_draft', None) and not getattr(args, 'refine_task', None)
            and not getattr(args, 'plan_coverage', False)))
    if args.role != 'code' or not getattr(args, 'plan', None):
        return False
    plan = json.loads(Path(args.plan).read_text())
    return any(plan.get(key, {}).get('todo') == getattr(args, 'todo', None)
               for key in ('recovery_patch', 'operational_retry'))


def apply(args, settings, cloud):
    """Reserve repair thinking and tool output without reducing the input allowance."""
    if cloud or args.model == 'gemma' or not is_repair(args):
        return
    from profiles import CEILINGS, WINDOWS
    keys = ('thinking', 'reasoning_budget', 'output_tokens', 'context')
    before = {key: settings[key] for key in keys}
    settings['thinking'] = 'on'
    budget = settings['reasoning_budget']
    # Explicit uncapped thinking (zero or the CLI switch) already exceeds a floor.
    uncapped = budget == 0 or getattr(args, 'uncapped_thinking', False)
    settings['reasoning_budget'] = budget if uncapped else max(MIN_THINKING, budget or 0)
    settings['output_tokens'] = max(settings['output_tokens'],
                                   (MIN_THINKING if uncapped else settings['reasoning_budget']) + 2048)
    needed = settings['input_tokens'] + settings['output_tokens'] + 8192
    if needed > settings['context']:
        available = [n for n in WINDOWS if needed <= n <= CEILINGS[args.model]]
        if not available:
            raise ValueError('Repair thinking/output reserves exceed the model window; split the task')
        settings['context'] = min(available)
    settings['repair_budget_policy'] = {'minimum_thinking_tokens': MIN_THINKING,
        'tool_output_reserve': 2048, 'requested': before,
        'effective': {key: settings[key] for key in keys}}
