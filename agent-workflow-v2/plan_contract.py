"""Validate the budgets and stopping policy used by the deterministic runner."""
import math

COMPONENTS = ('framework', 'shadow', 'source', 'tests', 'history')


def validate(task):
    """Reject unbounded execution and context estimates with no useful margin."""
    context = task['context']
    estimate = context.get('estimate', {})
    if set(estimate) != set(COMPONENTS):
        raise ValueError('V3 context.estimate needs framework/shadow/source/tests/history token estimates')
    if any(type(n) is not int or n < 0 for n in estimate.values()):
        raise ValueError('Context estimates must be nonnegative integer token counts')
    if estimate['framework'] < 6144:
        raise ValueError('Reserve at least 6144 estimated tokens for Pi instructions and tool schemas')
    margin = context.get('margin_tokens')
    minimum = max(1024, math.ceil(sum(estimate.values()) * .25))
    if type(margin) is not int or margin < minimum:
        raise ValueError(f'Context margin must be at least {minimum} tokens (25%, minimum 1024)')
    if sum(estimate.values()) + margin > context['max_input_tokens']:
        raise ValueError('Estimated input plus margin exceeds the reviewed input cap; split retrieval/task')
    policy = task.get('execution', {})
    if set(policy) != {'timeout_seconds', 'test_timeout_seconds', 'on_failure'}:
        raise ValueError('V3 execution needs timeout_seconds/test_timeout_seconds/on_failure')
    if type(policy['timeout_seconds']) is not int or not 30 <= policy['timeout_seconds'] <= 1200:
        raise ValueError('Todo timeout must be 30-1200 seconds')
    if type(policy['test_timeout_seconds']) is not int or not 1 <= policy['test_timeout_seconds'] <= 300:
        raise ValueError('Each test timeout must be 1-300 seconds')
    if policy['on_failure'] != 'replan':
        raise ValueError('Failed todos must stop and request evidence-backed replanning')


def summary(task):
    """Expose the reviewed split; these are estimates, never measured backend counts."""
    context = task['context']
    return {'estimate': context['estimate'], 'margin_tokens': context['margin_tokens'],
            'max_input_tokens': context['max_input_tokens'],
            'max_output_tokens': context['max_output_tokens'],
            'window_tokens': context.get('window_tokens', 98304)}
