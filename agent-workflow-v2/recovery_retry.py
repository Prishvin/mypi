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


def authorize_repair(root, folder, state):
    """Honor one explicit continuation after corrective execution failed, retaining history."""
    repairs = state.get('repairs', [])
    if state.get('status') != 'awaiting_user' or not repairs:
        raise ValueError('Allow-repair requires a stopped corrective execution')
    last = repairs[-1]
    current = Path(state['current_plan'])
    if (not last.get('review_result', {}).get('passed') or not current.is_file()
            or current.resolve() != Path(last['plan']).resolve()):
        raise ValueError('Use retry-review for failed generation; no executed corrective plan exists')
    evidence = Path(state['current_run']) / 'replan-request.json'
    packet = read(evidence)
    if (not packet or packet.get('project') != str(root.resolve()) or
            packet.get('current_snapshot') != scan(root, ['.'])['snapshot'] or
            Path(packet.get('plan', '')).resolve() != current.resolve() or
            packet.get('failed_todo', {}).get('id') != last['todo'] or
            last['todo'] not in state.get('spent_ids', [])):
        raise ValueError('Allow-repair evidence is stale or differs from the stopped corrective execution')
    state.setdefault('repair_authorizations', []).append({
        'epoch': time.time(), 'failed_plan': str(current), 'evidence': str(evidence),
        'reason': 'Explicit --allow-repair: one further review and corrective execution; prior allowance history preserved'})
    state['status'] = 'retrying_review'
    state.pop('reason', None)
    save(folder / 'recovery-state.json', state)
