"""Bound source observations for a failure reviewer to its pinned task evidence."""
import fcntl
import json
import os
from pathlib import Path
import retrieval
from project_map import scan

COMMANDS = {'read-symbol', 'read-symbols', 'read-symbols-across', 'read-file', 'variables', 'search'}
MAX_CALLS, MAX_TOTAL_BYTES, MAX_PAGE_BYTES = 6, 24000, 12000


def binding(root):
    """Validate the launched reviewer, frozen snapshot and task-local source scope."""
    if not os.environ.get('QWEN_WORKFLOW_SESSION') or not os.environ.get('QWEN_WORKFLOW_REPLAN_EVIDENCE'):
        raise ValueError('Source recovery needs a bound failure review session')
    session = Path(os.environ['QWEN_WORKFLOW_SESSION']).resolve()
    evidence = Path(os.environ['QWEN_WORKFLOW_REPLAN_EVIDENCE']).resolve()
    launch = json.loads((session / 'launch.json').read_text())
    if (os.environ.get('QWEN_WORKFLOW_ROLE') != 'architect' or launch.get('role') != 'architect'
            or launch.get('project') != str(root) or launch.get('session') != str(session)
            or launch.get('replan_evidence') != str(evidence)
            or evidence != session / 'replan-evidence.json'):
        raise ValueError('Source recovery needs this launched architect and pinned evidence')
    packet = json.loads(evidence.read_text())
    if packet.get('project') != str(root) or packet.get('current_snapshot') != scan(root, ['.'])['snapshot']:
        raise ValueError('Failure source evidence is stale or belongs to another project')
    task = packet['failed_todo']
    allowed = set(task['files'] + task['context'].get('interfaces', []))
    return session, allowed


def dispatch(root, args):
    """Reuse bounded native readers; never import or execute project code."""
    if args.command == 'read-symbol':
        return retrieval.read_symbol(root, args.path, args.name, args.offset)
    if args.command == 'read-symbols':
        return retrieval.read_symbols(root, args.path, args.names)
    if args.command == 'read-symbols-across':
        from retrieval_batch import read_across
        return read_across(root, args.paths, args.names)
    if args.command == 'read-file':
        return retrieval.read_page(root, args.path, args.offset)
    if args.command == 'variables':
        return retrieval.variables(root, args.path, args.query)
    return retrieval.search(root, args.paths, args.pattern, args.regex)


def read(root, args):
    """Serve at most six observations / 24 KB per reviewer with a durable audit."""
    root = root.resolve()
    if args.command not in COMMANDS or getattr(args, 'fixture_request', False):
        raise ValueError('Failure recovery supports bounded project source only')
    session, allowed = binding(root)
    paths = getattr(args, 'paths', None) or [args.path]
    if not 1 <= len(paths) <= 5:
        raise ValueError('Choose 1-5 explicit files from the failed task or its interfaces')
    for relative in paths:
        target = (root / relative).resolve()
        if (relative not in allowed or not target.is_relative_to(root)
                or not target.is_file() or target.stat().st_size > 1048576):
            raise ValueError('Recovery source must be a declared task file/interface below 1 MiB: ' + relative)
    with (session / 'recovery-source.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        receipt = session / 'recovery-source-reads.json'
        audit = json.loads(receipt.read_text()) if receipt.exists() else {'calls': [], 'bytes': 0}
        if len(audit['calls']) >= MAX_CALLS:
            raise ValueError('Failure-review source call budget exhausted; use collected evidence')
        result = dispatch(root, args)
        size = len(json.dumps(result, indent=2).encode())
        if size > MAX_PAGE_BYTES or audit['bytes'] + size > MAX_TOTAL_BYTES:
            raise ValueError('Failure-review source byte budget exceeded; select fewer symbols')
        audit['calls'].append({'command': args.command, 'paths': paths, 'bytes': size,
                               'selector': vars(args)})
        audit['bytes'] += size
        # CLI arguments include Path objects; audit stores selectors, never source bodies.
        receipt.write_text(json.dumps(audit, indent=2, default=str) + '\n')
    return {**result, 'readonly': True, 'recovery_budget': {
        'calls_used': len(audit['calls']), 'max_calls': MAX_CALLS,
        'bytes_used': audit['bytes'], 'max_bytes': MAX_TOTAL_BYTES}}
