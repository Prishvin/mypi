"""Detect stalled execution from measured changes, never from model success prose."""
import hashlib
import json


def digest(value):
    """Compare bounded evidence independently of timestamps and JSON field order."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def advance(saved, evidence, events):
    """Bound stalled rounds, with limited grace for distinct successful retrievals."""
    state = json.loads(json.dumps(saved)) if saved else {
        'seen': [], 'rounds': 0, 'compactions': 0, 'reads': [], 'errors': [], 'recent': []}
    signature = digest(evidence)
    changed = signature not in state['seen']
    if changed:
        state['seen'] = (state['seen'] + [signature])[-128:]
        state.update(rounds=0, compactions=0, reads=[], novel_reads=[])
    state.setdefault('novel_reads', [])
    for event in events:
        kind = event.get('kind')
        if not changed:
            if kind == 'round':
                state['rounds'] += 1
            if kind == 'compaction':
                state['compactions'] += 1
            if kind == 'tool' and event.get('tool') in {'source_query', 'project_map', 'skill_read'}:
                key = digest({'tool': event['tool'], 'selector': event.get('selector', {})})
                state['reads'] = (state['reads'] + [key])[-24:]
                if not event.get('error') and event.get('selector') and key not in state['novel_reads']:
                    state['novel_reads'] = (state['novel_reads'] + [key])[:4]
        if kind == 'tool':
            row = {key: event[key] for key in ('tool', 'selector', 'error') if key in event}
            state['recent'] = (state['recent'] + [row])[-8:]
            if event.get('error'):
                state['errors'] = (state['errors'] + [row])[-3:]
    repeated = max((state['reads'].count(key) for key in set(state['reads'])), default=0)
    grace = len(state['novel_reads'])
    limit = 4 + grace
    stop = state['rounds'] >= limit or (state['rounds'] >= 3 and (
        state['compactions'] >= 2 or repeated >= 3))
    status = 'stop' if stop else 'warning' if state['rounds'] >= 2 else 'continue'
    brief = {'status': status, 'rounds_without_progress': state['rounds'],
             'compactions_without_progress': state['compactions'], 'repeated_read_count': repeated,
             'retrieval_grace_rounds': grace, 'no_progress_round_limit': limit,
             'recent_tools': state['recent'], 'recent_errors': state['errors'],
             'tests': evidence.get('tests', []),
             'evidence_rule': 'Progress means a new scoped file-content or test-outcome fingerprint. '
                 'Identical tests, timestamps and reverting to seen content do not reset the counter. '
                 'Distinct successful reads grant at most four extra rounds, not accepted progress. '
                 'Tool history records observations, not inferred diagnoses or accepted correctness.'}
    if status != 'continue':
        brief['next_action'] = ('Stop for evidence-based review; preserve this investigation and frozen acceptance.'
            if stop else 'No new file or test outcome in two model rounds. Use the retrieved evidence for a scoped '
            'edit or executable test. Avoid rereading unchanged pages. If scope or the contract prevents '
            'a fix, state the blocker. Further unchanged rounds will stop for review.')
    state.update(signature=signature, brief=brief)
    return state
