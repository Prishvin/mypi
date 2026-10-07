"""Describe verified file/test progress without inferring completion from model prose."""


def describe(contract, declared, identity):
    """Keep an exact bounded inventory and distinguish absent evidence from failed tests."""
    before = contract['declared_hashes']
    files = []
    for path in contract['task']['files']:
        digest = declared.get(path)
        status = 'absent' if digest is None else 'new' if before.get(path) is None else (
            'unchanged' if digest == before[path] else 'modified')
        files.append(dict(path=path, status=status, sha256=digest))
    pending = [row['path'] for row in files if row['status'] == 'absent'
               and before.get(row['path']) is None and row['path'] != 'architecture.md']
    evidence = contract.get('evidence', {})
    rows = evidence.get('results', [])
    fresh = evidence.get('snapshot') == identity and evidence.get('finished_snapshot') == identity
    status = 'not_run' if not rows else 'stale' if not fresh else (
        'passed' if len(rows) == len(contract['task']['tests']) and all(
            r['exit_code'] == 0 and r.get('tests_collected') != 0 for r in rows) else 'failed')
    action = ('Create the missing declared files before repeatedly revising existing source; '
              'write the frozen tests and measure behavior instead of simulating it in reasoning.') if pending else (
              'Run workflow_test for current evidence before speculative rewrites.' if status in {'not_run', 'stale'}
              else 'Repair the reported test failures within scope.' if status == 'failed'
              else 'Resolve only remaining gate violations; preserve passing implementation.')
    return dict(files=files, pending_files=pending, tests_status=status, next_action=action)
