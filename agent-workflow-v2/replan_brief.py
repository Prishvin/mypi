"""Distill recovery context while retaining the complete local evidence packet."""
import copy


def distill(packet):
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
    return brief
