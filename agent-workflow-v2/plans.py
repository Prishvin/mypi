"""Persist architectural plans and hand off one atomic todo to local Qwen."""
import json
from pathlib import Path
from project_map import scan
from tasks import validate_paths
from profiles import PRESETS, WINDOWS, MAX_TASK_INPUT
from research_briefs import read_brief


def validate_context(root: Path, task: dict) -> None:
    """Require a small retrieval recipe and explicit input/output reserves per todo."""
    context = task.get('context', {})
    interfaces = context.get('interfaces', [])
    symbols = context.get('symbols', [])
    references = context.get('reference_files', [])
    if context.get('knowledge_topics'):
        from knowledge_context import select
        select(root, context['knowledge_topics'])
    if len(interfaces) > 6 or len(symbols) > 8 or len(references) > 5:
        raise ValueError('Split retrieval: max 6 interfaces, 8 symbols, 5 reference files per todo')
    validate_paths(root, interfaces + references + [s['path'] for s in symbols])
    briefs = context.get('research_briefs', [])
    if len(briefs)>2:
        raise ValueError('At most two research briefs per todo')
    for path in briefs:
        read_brief(Path(path))
    for key, limit in [('max_input_tokens', MAX_TASK_INPUT), ('max_output_tokens', 32768)]:
        if type(context.get(key)) is not int or not 512 <= context[key] <= limit:
            raise ValueError(f'{key} must be 512-{limit}; split larger tasks')
    if 'preset' in context and context['preset'] not in PRESETS:
        raise ValueError('Unknown context preset')
    if 'window_tokens' in context:
        if context['window_tokens'] not in WINDOWS:
            raise ValueError('Invalid per-task context window')
        if context['max_input_tokens'] + context['max_output_tokens'] + 8192 > context['window_tokens']:
            raise ValueError('Task budgets exceed its context window')
    if context.get('thinking', 'on') not in ['on', 'off']:
        raise ValueError('Invalid task thinking setting: use literal "on" or "off"; reasoning_effort is a separate field')
    if context.get('reasoning_effort', 'medium') not in ['low', 'medium', 'xhigh']:
        raise ValueError('Invalid task reasoning effort: use literal "low", "medium" or "xhigh"')
    cap = context.get('reasoning_budget_tokens')
    if cap is not None and (type(cap) is not int or not 0 <= cap <= context['max_output_tokens']-2048):
        raise ValueError('Thinking cap must leave 2048 tokens for edits/tool calls')
    if cap is not None and context.get('thinking') == 'off':
        raise ValueError('A thinking-off task cannot specify a separate thinking cap')


def validate_granularity(task: dict) -> None:
    """Require a small implementation recipe and explicit testing strategy in v2 plans."""
    steps = task.get('steps', [])
    if not isinstance(steps, list) or not 2 <= len(steps) <= 6 or not all(isinstance(x, str) and x.strip() for x in steps):
        raise ValueError('V2 todos require 2-6 concrete implementation steps')
    estimate = task.get('estimated_changed_lines')
    if type(estimate) is not int or not 1 <= estimate <= 300:
        raise ValueError('V2 todo patch estimate must be 1-300 lines; split larger changes')
    if not isinstance(task.get('test_strategy'), str) or not task['test_strategy'].strip():
        raise ValueError('V2 todos require an explicit behavior/regression test strategy')
    if not isinstance(task.get('assumptions'), list) or not all(isinstance(x, str) and x.strip() for x in task['assumptions']):
        raise ValueError('V2 todos require an assumptions list; use [] when none')


def validate_coverage(task: dict) -> None:
    """Require observable acceptance cases and a declared test for each one."""
    criteria = task['acceptance']
    identifiers = set()
    for case in criteria:
        if not isinstance(case, dict) or not all(case.get(k) for k in ['id', 'given', 'when', 'then']):
            raise ValueError('Acceptance needs id/given/when/then for each case')
        if case['id'] in identifiers:
            raise ValueError('Acceptance ids must be unique within a todo')
        identifiers.add(case['id'])
    covered = set()
    for row in task.get('coverage', []):
        if row.get('criterion') not in identifiers:
            raise ValueError(f"Task {task.get('id')}: unknown acceptance id {row.get('criterion')!r}; use an exact criterion id")
        index = row.get('test')
        count = len(task['tests'])
        if not isinstance(index, int) or not 0 <= index < count:
            raise ValueError(f"Task {task.get('id')}: coverage.test={index!r} is invalid for {count} test command(s). "
                             f"Allowed zero-based command indices: {list(range(count))}. Each tests element is one argv "
                             "COMMAND, even if it names several fixture files. With one command, use literal 0 for every criterion.")
        covered.add(row['criterion'])
    if covered != identifiers:
        raise ValueError('Every acceptance criterion needs a planned test')


def save(root: Path, prefixes: list[str], plan: dict, output: Path) -> dict:
    """Validate task boundaries and reset planned todos; never overwrite an existing plan."""
    if output.exists():
        raise ValueError('Plan already exists; use a new planning session')
    from plan_shape import canonical
    plan=canonical(plan)
    if not plan.get('goal') or not plan.get('architecture') or not plan.get('tasks'):
        raise ValueError('Plan needs goal, architecture and tasks')
    if plan.get('plan_version', 1) not in [1, 2, 3]:
        raise ValueError('Unsupported plan version')
    known = set()
    for task in plan['tasks']:
        identifier = task.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in known:
            raise ValueError('Todo ids must be unique nonempty strings')
        if not set(task.get('depends_on', [])) <= known:
            raise ValueError('Dependencies must refer to preceding todos')
        if not task.get('goal') or not task.get('acceptance') or not task.get('tests'):
            raise ValueError('Each todo requires goal, acceptance and tests')
        files = task.get('files', [])
        if not files or len(set(files)) > 8:
            raise ValueError('Each todo needs 1-8 exact file paths')
        validate_paths(root, files)
        validate_context(root, task)
        validate_coverage(task)
        if plan.get('plan_version') in [2, 3]:
            validate_granularity(task)
        if plan.get('plan_version') == 3:
            from plan_contract import validate
            validate(task)
        for command in task['tests']:
            if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
                raise ValueError('Tests must be argv lists')
        task['status'] = 'todo'
        known.add(identifier)
    from tasks import readonly_tests
    fixtures = readonly_tests(root, [argv for task in plan['tasks'] for argv in task['tests']])
    plan.update(project=str(root.resolve()), snapshot=scan(root, prefixes)['snapshot'],
                acceptance_fixtures=fixtures)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2))
    return {'plan': str(output), 'todos': len(plan['tasks']), 'snapshot': plan['snapshot']}


def select(path: Path, identifier: str) -> dict:
    """Hand off an unfinished todo only after its declared dependencies pass."""
    plan = json.loads(path.read_text())
    matches = [t for t in plan['tasks'] if t['id'] == identifier]
    if len(matches) != 1 or matches[0]['status'] != 'todo':
        raise ValueError('Select one existing unfinished todo')
    task = matches[0]
    done = {t['id'] for t in plan['tasks'] if t['status'] == 'done'}
    if not set(task.get('depends_on', [])) <= done:
        raise ValueError('Complete dependencies before this todo')
    return {k: v for k, v in task.items() if k not in {'status', 'depends_on', 'baseline'}}


def start_attempt(path: Path, identifier: str, state: Path) -> None:
    """Reuse an unfinished todo's original patch baseline across focused retries."""
    from tasks import inherit_baseline
    plan = json.loads(path.read_text())
    task = next(t for t in plan['tasks'] if t['id'] == identifier)
    if task.get('baseline'):
        inherit_baseline(state, Path(task['baseline']))
    else:
        task['baseline'] = str(state)
        path.write_text(json.dumps(plan, indent=2))


def complete(path: Path, identifier: str, gate: dict, session: Path) -> None:
    """Mark a todo done only with passing tests and a current shadow."""
    if not gate.get('passed'):
        raise ValueError('A failed completion gate cannot finish a todo')
    plan = json.loads(path.read_text())
    select(path, identifier)
    task = next(t for t in plan['tasks'] if t['id'] == identifier)
    task.update(status='done', evidence=str(session / 'final-gate.json'),
                shadow_snapshot=gate['shadow_snapshot'])
    path.write_text(json.dumps(plan, indent=2))
