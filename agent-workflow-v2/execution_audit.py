"""Distill mechanical execution history for recovery without sending source or reasoning."""
import hashlib
import json
from pathlib import Path


def summarize(path, files):
    """Read JSONL once and retain only counts, declared paths and bounded tool errors."""
    if not path or not Path(path).is_file():
        return {}
    mutations, pending, errors = {}, {}, []
    compactions = 0
    with Path(path).open(errors='replace') as stream:
        for line in stream:
            if not line.startswith('{') or '"message_update"' in line[:80]:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') == 'compaction_end' and not event.get('aborted'):
                compactions += 1
            if event.get('type') == 'tool_execution_start':
                args = event.get('args', {})
                if event.get('toolName') in {'write', 'edit'} and args.get('path') in files:
                    content = args.get('content')
                    digest = hashlib.sha256(content.encode()).hexdigest() if isinstance(content, str) else None
                    pending[event.get('toolCallId')] = (args['path'], digest)
            if event.get('type') != 'tool_execution_end':
                continue
            mutation = pending.pop(event.get('toolCallId'), None)
            if event.get('isError'):
                text = ' '.join(b.get('text', '') for b in event.get('result', {}).get('content', [])
                                if b.get('type') == 'text')
                errors.append({'tool': event.get('toolName'), 'error': text.split('Received arguments:')[0][:240]})
                errors = errors[-4:]
            elif mutation:
                name, digest = mutation
                row = mutations.setdefault(name, {'successful_mutations': 0, 'identical_consecutive_writes': 0})
                row['successful_mutations'] += 1
                if digest and digest == row.get('last_write_sha256'):
                    row['identical_consecutive_writes'] += 1
                row['last_write_sha256'] = digest
    return dict(compactions=compactions, mutations=mutations, recent_tool_errors=errors,
                note='Counts are observed tool outcomes, not task acceptance. Source bodies and reasoning stay local.')
