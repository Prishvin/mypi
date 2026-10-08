"""Re-read recorded diagnostics for recovery while preserving the original packet."""
import copy
import hashlib
import json
from pathlib import Path


def refresh(packet):
    """Bind a refreshed error brief to the same failed session and frozen contract."""
    if not packet.get('session'):
        return copy.deepcopy(packet)
    session = Path(packet['session']).resolve()
    state_path = session/'task-state.json'
    state = json.loads(state_path.read_text())
    if Path(state.get('before', {}).get('root', '')).resolve() != Path(packet['project']).resolve():
        raise ValueError('Diagnostic session belongs to a different project')
    for key in ('id', 'files', 'acceptance', 'tests'):
        if state.get('task', {}).get(key) != packet.get('failed_todo', {}).get(key):
            raise ValueError('Diagnostic session differs from failed contract: '+key)
    receipts = []
    for row in state.get('evidence', {}).get('results', []):
        if row.get('argv') not in state['task']['tests']:
            raise ValueError('Diagnostic command is outside the failed contract')
        path = Path(row['log']).resolve()
        if path.parent != session or not path.is_file():
            raise ValueError('Diagnostic log must belong to the failed session')
        receipts.append({'log': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    from runner_evidence import failed_tests
    result = copy.deepcopy(packet)
    result['failed_tests'] = failed_tests(str(session))
    result['diagnostics_refresh'] = {'method': 'Native bounded exception/count extraction from recorded logs',
        'session': str(session), 'state_sha256': hashlib.sha256(state_path.read_bytes()).hexdigest(),
        'logs': receipts, 'original_packet_preserved': True}
    return result
