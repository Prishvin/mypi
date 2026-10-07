"""Detect stalled execution from measured changes, never from model success prose."""
import hashlib
import json


def digest(value):
    """Compare bounded evidence independently of timestamps and JSON field order."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def advance(saved, evidence, events):
    """Warn after two unchanged rounds; stop after four or repeated compaction."""
    state = json.loads(json.dumps(saved)) if saved else {
        'seen': [], 'rounds': 0, 'compactions': 0, 'reads': [], 'errors': [], 'recent': []}
    signature = digest(evidence)
    changed = signature not in state['seen']
    if changed:
        state['seen'] = (state['seen'] + [signature])[-128:]
        state.update(rounds=0, compactions=0, reads=[])
    for event in events:
        kind = event.get('kind')
        if not changed:
            if kind == 'round':
                state['rounds'] += 1
            if kind == 'compaction':
                state['compactions'] += 1
            if kind == 'tool' and event.get('tool') in {'source_query', 'project_map', 'skill_read'}:
                state['reads'] = (state['reads'] + [digest(event.get('selector', {}))])[-24:]
        if kind == 'tool':
            row = {key: event[key] for key in ('tool', 'selector', 'error') if key in event}
            state['recent'] = (state['recent'] + [row])[-8:]
            if event.get('error'):
                state['errors'] = (state['errors'] + [row])[-3:]
    repeated = max((state['reads'].count(key) for key in set(state['reads'])), default=0)
    stop = state['rounds'] >= 4 or (state['rounds'] >= 3 and (
        state['compactions'] >= 2 or repeated >= 3))
    status = 'stop' if stop else 'warning' if state['rounds'] >= 2 else 'continue'
    brief = {'status': status, 'rounds_without_progress': state['rounds'],
             'compactions_without_progress': state['compactions'], 'repeated_read_count': repeated,
             'recent_tools': state['recent'], 'recent_errors': state['errors'],
             'tests': evidence.get('tests', []),
             'evidence_rule': 'Progress means a new scoped file-content or test-outcome fingerprint. '
                 'Identical tests, timestamps and reverting to seen content do not reset the counter. '
                 'Tool history records observations, not inferred diagnoses or accepted correctness.'}
    if status != 'continue':
        brief['next_action'] = ('Stop for evidence-based review; preserve this investigation and frozen acceptance.'
            if stop else 'No measured progress in two model rounds. Use the retrieved evidence for a scoped '
            'edit or executable test. Avoid rereading unchanged pages. If scope or the contract prevents '
            'a fix, state the blocker. Further unchanged rounds will stop for review.')
    state.update(signature=signature, brief=brief)
    return state
