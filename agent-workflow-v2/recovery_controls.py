"""Expose measured executor controls to recovery without launcher prompts or source."""


def summarize(launch, metrics):
    """Distinguish inherited thinking limits and forced closes from planning ceilings."""
    settings = launch.get('effective_settings', {})
    controls = {key: settings[key] for key in ('context', 'input_tokens', 'output_tokens',
        'thinking', 'reasoning', 'reasoning_budget', 'profile') if key in settings}
    completed = [row for row in metrics.get('native_requests', []) if not row.get('request_cancelled')]
    guarded = [row['thinking_guard'] for row in completed if isinstance(row.get('thinking_guard'), dict)]
    return {'effective_executor_controls': controls, 'thinking_guard_observations': {
        'completed_requests': len(completed), 'requests_with_guard_telemetry': len(guarded),
        'budget_hits': sum(row.get('engaged') == 'budget' for row in guarded),
        'reported_budget_tokens': sorted({row['budget_tokens'] for row in guarded
                                         if isinstance(row.get('budget_tokens'), int)}),
        'note': 'Missing guard telemetry is unknown, not zero cap hits. Frequent forced closes '
                'do not by themselves prove that a larger cap improves correctness.'}}
