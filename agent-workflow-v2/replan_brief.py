"""Distill recovery context while retaining the complete local evidence packet."""
import copy

REVISABLE_FIELDS = ('steps', 'assumptions', 'test_strategy', 'estimated_changed_lines',
                    'context', 'execution', 'repair_strategy_review')


def separate_strategy(task):
    """Keep failed repair hypotheses out of the mandatory contract presented to a reviewer."""
    contract = {key: value for key, value in task.items()
                if key not in REVISABLE_FIELDS and key not in ('status', 'evidence', 'baseline', 'result')}
    strategy = {key: task[key] for key in REVISABLE_FIELDS if key in task}
    return contract, {'authority': 'Previous unsuccessful strategy, not additional requirements. '
        'Its diagnoses, test-immutability claims and read/edit restrictions are revisable hypotheses; '
        'check them independently against failed_contract and observed evidence.', **strategy}


def distill(packet, focused=False):
    """Keep pending contracts and observed failures; omit duplicated telemetry."""
    brief = copy.deepcopy(packet)
    failed = brief.pop('failed_todo', {})
    brief['failed_todo_id'] = failed.get('id')
    metric = brief.get('metrics', {})
    native = metric.get('native_requests', [])
    brief['metrics'] = {key: metric[key] for key in (
        'requests', 'input_tokens_sum', 'cache_read_tokens_sum',
        'output_tokens_sum', 'reasoning_tokens_sum', 'request_seconds',
        'server_rss_peak_sampled_bytes') if key in metric}
    brief['metrics']['largest_completed_prompt_tokens'] = max(
        (row.get('prompt_tokens') or 0 for row in native), default=0)
    brief['metrics']['note'] = 'Per-request telemetry remains in the local evidence packet.'
    for task in brief.get('remaining', []):
        for key in ('status', 'evidence', 'baseline', 'result'):
            task.pop(key, None)
    for task in brief.get('completed', []):
        for key in ('tests', 'execution', 'evidence'):
            task.pop(key, None)
    regression = brief.pop('regression', None)
    if regression and not regression.get('passed'):
        brief['regression_failure'] = {
            'reason': regression.get('reason'),
            'tests': [row for row in regression.get('tests', []) if row.get('exit_code')],
        }
    brief['evidence_note'] = (
        'This is a deterministic context brief. The full packet remains local and '
        'validates scope, frozen acceptance, tests and accepted regressions. '
        'Pending contracts below retain their exact acceptance objects and test argv.')
    if focused:
        remaining = brief.pop('remaining', [])
        selected = next((task for task in remaining if task['id'] == failed.get('id')), failed)
        brief['failed_contract'], brief['previous_attempt_strategy'] = separate_strategy(selected)
        brief['remaining_overview'] = [{key: task[key] for key in ('id', 'goal', 'depends_on', 'files')
                                      if key in task} for task in remaining]
        brief['evidence_note'] = ('Only the failed todo can be repaired. failed_contract contains mandatory scope, '
            'acceptance and test commands. previous_attempt_strategy contains revisable decisions from an '
            'unsuccessful attempt, not new frozen requirements. All other pending contracts remain local; '
            'Python preserves them exactly. Submit failure_analysis and flat changed fields, not the whole plan.')
        if metric.get('admission_estimate'):
            brief['metrics']['admission_estimate'] = copy.deepcopy(metric['admission_estimate'])
    return brief
