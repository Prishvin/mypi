"""Explicitly authorize another review after a failed generation, preserving the repair allowance."""
import time
from pathlib import Path
from project_map import scan
from runner_process import read, save


def authorize(root, folder, state):
    """Retry only failed review transport, never repeat an already executed repair automatically."""
    repairs = state.get('repairs', [])
    if state.get('status') not in {'awaiting_user', 'reviewing'} or not repairs:
        raise ValueError('Retry-review requires a stopped failure review')
    last = repairs[-1]
    if last.get('review_result', {}).get('passed') or Path(last['plan']).exists():
        raise ValueError('A generated plan exists; validate it instead of retrying review')
    evidence = Path(state['current_run']) / 'replan-request.json'
    packet = read(evidence)
    if (not packet or packet.get('project') != str(root.resolve()) or
            packet.get('current_snapshot') != scan(root, ['.'])['snapshot'] or
            packet.get('failed_todo', {}).get('id') != last['todo'] or
            Path(last['evidence']).resolve() != evidence.resolve()):
        raise ValueError('Retry-review evidence is stale or differs from the stopped review')
    state.setdefault('review_retry_authorizations', []).append({
        'epoch': time.time(), 'prior_plan': last['plan'], 'evidence': str(evidence),
        'reason': 'Explicit --retry-review after failed generation; execution allowance preserved'})
    state['status'] = 'retrying_review'
    state.pop('reason', None)
    save(folder / 'recovery-state.json', state)
