"""Turn a user's request into one clarified, researched architecture request."""
from intake_service import refine
from research_service import research
from runner_process import save


def prepare(project, request, output, planner, timeout, clarifier='auto', researcher='auto',
            answers=None, interactive=False, refresh=False):
    """Stop at unanswered ambiguity; researching never answers on the user's behalf."""
    for name in (clarifier, researcher):
        if name not in ('auto', 'chatgpt', 'qwen', 'off'):
            raise ValueError('Initial stage backend must be auto, chatgpt, qwen or off')
    state = {'passed': True, 'original_request': request}
    if clarifier != 'off':
        intake = refine(project, request, output.with_suffix('.intake'),
                        planner if clarifier == 'auto' else clarifier, answers, interactive, min(timeout, 300))
        state['intake'] = intake
        if intake['status'] != 'ready':
            state.update(passed=False, stage=intake['status'])
            save(output.with_suffix('.pipeline-result.json'), state)
            return state
        request = intake['refined_prompt']
    state['refined_prompt'] = request
    if researcher != 'off':
        result = research(project, request, output.with_suffix('.research'),
                          planner if researcher == 'auto' else researcher, min(timeout, 300), refresh)
        state['research'] = result
        if not result['passed']:
            if result.get('timed_out') or result.get('exit_code') == 124:
                reason = 'Research timed out before saving its verified draft.'
            elif result.get('exit_code'):
                reason = f"Research Pi process exited with code {result['exit_code']} before saving its verified draft."
            else:
                reason = 'Research did not save its required verified draft.'
            if result.get('log'):
                reason += ' Process log: ' + result['log']
            state.update(passed=False, stage='research_failed', error=reason)
    save(output.with_suffix('.pipeline-result.json'), state)
    return state
