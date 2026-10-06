"""Pure checks for file/function size and bounded task scope."""


def validate_change(before: dict, after: dict, allowed: list[str],
                    max_files=8, file_limit=300, function_limit=60) -> dict:
    """Reject new oversize code; permit existing oversize code only without growth."""
    old = {f['path']: f for f in before['files']}
    new = {f['path']: f for f in after['files']}
    changed = sorted(p for p in old.keys() | new.keys()
                     if old.get(p, {}).get('sha256') != new.get(p, {}).get('sha256'))
    for key in ['architecture', 'knowledge']:
        if before.get(key, {}) != after.get(key, {}):
            changed = sorted(set(changed) | {key + '.md'})
    violations, warnings = [], []
    if len(changed) > max_files:
        violations.append(f'Task changes {len(changed)} files; limit is {max_files}')
    for path in changed:
        if path not in allowed:
            violations.append(f'Outside declared scope: {path}')
        record = new.get(path)
        if record is None:
            continue
        previous = old.get(path, {})
        if record.get('error'):
            violations.append(f'Cannot parse {path}: {record["error"]}')
        if record['lines'] > max(file_limit, previous.get('lines', 0)):
            violations.append(f'File size grows above limit: {path} ({record["lines"]})')
        elif record['lines'] > file_limit:
            warnings.append(f'Existing large file: {path} ({record["lines"]})')
        if record.get('bytes', 0) > max(32768, previous.get('bytes', 0)):
            violations.append(f'File size grows above 32 KiB: {path}')
        previous_symbols = {s['name']: s for s in previous.get('symbols', [])}
        for symbol in record.get('symbols', []):
            if symbol['kind'] != 'function':
                continue
            original = previous_symbols.get(symbol['name'], {})
            if symbol['lines'] > max(function_limit, original.get('lines', 0)):
                violations.append(f'Function size grows above limit: {path}:{symbol["name"]} '
                                  f'({symbol["lines"]} lines; limit {max(function_limit, original.get("lines", 0))}; '
                                  'nested function bodies count toward the enclosing function)')
            if symbol['description'] == '[description missing]' and '<callback@' not in symbol['name']:
                if not original:
                    violations.append(f'New function needs a brief description: {path}:{symbol["name"]}')
                elif original.get('description') != '[description missing]':
                    violations.append(f'Function description was removed: {path}:{symbol["name"]}')
                else:
                    warnings.append(f'Existing function lacks a brief: {path}:{symbol["name"]}')
    return {'passed': not violations, 'changed': changed,
            'violations': violations, 'warnings': warnings}
