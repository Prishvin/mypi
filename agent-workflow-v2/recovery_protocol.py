"""Describe the launched failure agent and validate its bounded disposition."""
import copy
import json
from pathlib import Path
from recovery_source import MAX_CALLS, MAX_TOTAL_BYTES, MAX_PAGE_BYTES

POLICY = {'version': 1, 'agent': 'failure-recovery', 'provider': 'selected-planner'}
CATEGORIES = ('implementation', 'test_assumption', 'tool_usage', 'context_budget',
              'deadline', 'framework', 'environment', 'contract_conflict', 'unknown')
ACTIONS = ('repair', 'needs_user', 'framework_fix', 'environment_fix')
CONTEXT_ACTIONS = ('keep', 'retrieve_scoped', 'reduce_packet', 'increase_within_limits')


def validate(value, packet, action=None):
    """Require evidence and a supported disposition; this is not a truth verifier."""
    if value is None and packet.get('failure_recovery_policy', {}).get('version') != 1:
        return None
    keys = {'category', 'action', 'summary', 'evidence', 'uncertainties', 'context_action'}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('recovery_decision needs category, action, summary, evidence, uncertainties and context_action')
    for key, choices in [('category', CATEGORIES), ('action', ACTIONS), ('context_action', CONTEXT_ACTIONS)]:
        if value[key] not in choices:
            raise ValueError('Unsupported recovery_decision.' + key)
    if action and value['action'] != action:
        raise ValueError('Use recovery_report for an escalation; plan_store requires action=repair')
    if not isinstance(value['summary'], str) or not 40 <= len(value['summary'].strip()) <= 1600:
        raise ValueError('Recovery summary needs 40–1600 characters')
    for key, minimum in [('evidence', 1), ('uncertainties', 0)]:
        if not isinstance(value[key], list) or not minimum <= len(value[key]) <= 5:
            raise ValueError('Recovery ' + key + ' must be a bounded string array')
        if any(not isinstance(v, str) or not 10 <= len(v.strip()) <= 800 for v in value[key]):
            raise ValueError('Recovery evidence/uncertainties need 10–800 characters per item')
    if value['action'] == 'repair' and value['category'] in ('framework', 'environment', 'contract_conflict'):
        raise ValueError('This cause requires escalation; the task executor cannot repair mypi, its environment or frozen requirements')
    return copy.deepcopy(value)


def manifest(launch, packet, tools):
    """Derive budgets, scope and skill availability from this immutable launch."""
    from skill_registry import catalog
    from planning_limits import limits
    from profiles import MAX_TASK_INPUT, WINDOWS
    provider = 'chatgpt' if launch['cloud'] else 'qwen'
    task = packet['failed_todo']
    return {'version': 1, 'agent': 'failure-recovery', 'provider': provider,
        'provider_selection': 'Inherits the project planner; does not change the executor.',
        'tools': tools.split(','),
        'review_limits': {k: launch[k] for k in ('context', 'input_budget', 'output_budget',
            'thinking', 'reasoning', 'reasoning_budget_tokens', 'timeout_seconds')},
        'packet_selection_limits': {k: limits(provider, 'recovery')[k] for k in ('packet', 'shadow')},
        'local_executor_limits': {'model_context_ceiling': launch.get('local_model_context_ceiling'),
            'max_input_tokens': MAX_TASK_INPUT, 'max_output_tokens': 32768,
            'supported_task_windows': sorted(WINDOWS),
            'failed_task_budgets': {k: v for k, v in task['context'].items() if k in
                ('max_input_tokens', 'max_output_tokens', 'window_tokens', 'reasoning_budget_tokens', 'thinking', 'reasoning_effort')}},
        'source_reads': {'allowed_files': sorted(set(task['files'] + task['context'].get('interfaces', []))),
            'max_calls': MAX_CALLS, 'max_page_bytes': MAX_PAGE_BYTES, 'max_total_bytes': MAX_TOTAL_BYTES,
            'actions': ['symbol', 'file', 'variables', 'search'],
            'binding': 'Current source snapshot; no arbitrary filesystem, shell or fixture execution.'},
        'skills': catalog(Path(launch['runtime']), 'architect'),
        'actions': {'repair': 'plan_store: revise only failed todo; Python preserves remaining contracts and validates budgets.',
            'needs_user': 'recovery_report: stop with a precise contract/scope question.',
            'framework_fix': 'recovery_report: preserve reproducible mypi/tool evidence; stop for maintainer.',
            'environment_fix': 'recovery_report: identify the missing/unhealthy dependency; stop for operator.'},
        'native_automation': ['After-edit architecture/shadow/map refresh', 'Frozen tests and task gate',
            'Regression checks before next todo', 'Publication verification and planner shutdown',
            'One automatic corrective execution per failed contract; further attempts need authorization'],
        'operator_only': ['Change model server or installed dependencies', 'Change mypi code or tool schemas',
            'Accept a saved review after failed handoff (--accept-review)',
            'Retry failed review generation (--retry-review)', 'Authorize another failed corrective run (--allow-repair)',
            'Change frozen scope/acceptance or split executed contracts'],
        'budget_rules': ['Review limits above are effective; packet_selection_limits bound selected evidence.',
            'Budget input includes system, skills, tools, selected evidence and history; tokens are not bytes.',
            'Executor budgets are separate from reviewer budgets, including cloud reviews of local execution.',
            'Future local tasks: input+output+8192 <= window; thinking is inside output with >=2048 for tools.',
            'Estimate framework >=6144; margin >=max(1024,ceil(estimate_total*0.25)); estimate+margin <= input.',
            'Local repairs keep thinking on with >=8192 tokens (or explicitly uncapped); no padding to the cap.']}


def write_manifest(session, launch, packet, tools):
    """Keep the exact capability inventory in local evidence and the model prompt."""
    value = manifest(launch, packet, tools)
    path = Path(session) / 'recovery-capabilities.json'
    path.write_text(json.dumps(value, indent=2) + '\n')
    return str(path)
