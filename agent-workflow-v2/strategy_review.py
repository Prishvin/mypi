"""Validate an evidence-led change of repair strategy without changing acceptance."""
import copy
import json

POLICY = {'version': 1, 'mode': 'strategy_review',
          'purpose': 'Compare expectations with observed reality before the first corrective execution.'}
STATUSES = {'supported', 'implementation_gap', 'test_assumption', 'unknown', 'contract_conflict'}
FIELDS = {'expectation_checks', 'abandoned_assumptions', 'strategy_change', 'first_check', 'stop_condition'}


def text(value, name, minimum=20, maximum=1800):
    """Reject empty, oversized or untyped explanations at the Python boundary."""
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f'strategy_review.{name} must be {minimum}–{maximum} characters')


def validate(packet, fields):
    """Check report structure, contract references and a changed executable strategy."""
    report = fields.get('strategy_review')
    required = packet.get('strategy_review_policy', {}).get('version') == 1
    if report is None and not required:
        return None  # Historical pinned reviews keep their original protocol.
    if not isinstance(report, dict) or set(report) != FIELDS:
        raise ValueError('strategy_review requires expectation_checks, abandoned_assumptions, '
                         'strategy_change, first_check and stop_condition')
    if len(json.dumps(report).encode()) > 10000:
        raise ValueError('strategy_review exceeds 10000 bytes; retain only decisive evidence')
    checks = report['expectation_checks']
    if not isinstance(checks, list) or not 1 <= len(checks) <= 16:
        raise ValueError('strategy_review.expectation_checks needs 1–16 affected criteria')
    criteria = {case['id'] for case in packet['failed_todo']['acceptance']}
    seen = set()
    for row in checks:
        if not isinstance(row, dict) or set(row) != {'criterion', 'status', 'evidence'}:
            raise ValueError('Each expectation check needs criterion, status and evidence')
        if not isinstance(row['criterion'], str) or row['criterion'] not in criteria or row['criterion'] in seen:
            raise ValueError('Expectation checks must name distinct frozen criterion IDs')
        seen.add(row['criterion'])
        if not isinstance(row['status'], str) or row['status'] not in STATUSES:
            raise ValueError('Unknown strategy_review expectation status')
        text(row['evidence'], 'expectation_checks.evidence')
        if row['status'] == 'contract_conflict':
            raise ValueError('Frozen contract conflict needs user-directed replanning; no corrective plan accepted')
    abandoned = report['abandoned_assumptions']
    if not isinstance(abandoned, list) or len(abandoned) > 8:
        raise ValueError('strategy_review.abandoned_assumptions must be an array of at most 8 strings')
    for item in abandoned:
        text(item, 'abandoned_assumptions', minimum=10, maximum=1000)
    for key in ('strategy_change', 'first_check', 'stop_condition'):
        text(report[key], key)
    steps = fields.get('steps')
    if (not isinstance(steps, list) or len(steps) < 2 or steps[0] != report['first_check']
            or steps == packet['failed_todo'].get('steps')):
        raise ValueError('Strategy repair needs changed steps beginning with the exact first_check; '
                         'budget-only changes are insufficient')
    return copy.deepcopy(report)
