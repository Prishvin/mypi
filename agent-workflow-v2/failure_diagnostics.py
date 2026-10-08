"""Distill native test failures without losing decorated exceptions among names."""
import re

ANSI = re.compile(r'\x1b\[[0-9;]*m')
EXCEPTION = re.compile(r'^(?:[\w.]*Error|[\w.]*Exception)(?:\s+\[[^\]\r\n]{1,80}\])?:')
PREFIXES = ('FAILED ', 'ERROR:', 'FAIL:', 'Ran ', 'OK', 'not ok ', '✖ ',
            'error:', 'failureType:', 'expected:', 'actual:', 'operator:')


def summarize(text):
    """Prioritize unique exception causes, then retain other bounded observations."""
    lines = [ANSI.sub('', line).strip() for line in text.splitlines()]
    causes, other = [], []
    for line in lines:
        if EXCEPTION.match(line):
            if line[:300] not in causes:
                causes.append(line[:300])
        elif line.startswith(PREFIXES) and line != '✖ failing tests:':
            # Node repeats the same test name in its failure details.
            value = re.sub(r'\s+\([\d.]+ms\)$', '', line)[:300]
            if value not in other:
                other.append(value)
    selected = causes[:8] + other[:max(0, 16-min(8, len(causes)))]
    counts = {}
    for line in lines:
        match = re.fullmatch(r'(?:#|ℹ) (tests|pass|fail|cancelled|skipped|todo) (\d+)', line)
        if match:
            counts[match[1]] = int(match[2])
        match = re.search(r'\bRan (\d+) tests?\b', line)
        if match:
            counts['tests'] = int(match[1])
    return {'observations': selected, 'test_summary': counts,
            'diagnostic_omissions': {'causes': max(0, len(causes)-8),
                                   'other_observations': max(0, len(other)-(16-min(8, len(causes))))}}
