"""Apply model-authored recovery changes to one failed todo, retaining the plan locally."""
import copy
import json
from pathlib import Path
from plan_draft import apply, digest
from project_map import scan

FIELDS = {'steps', 'assumptions', 'test_strategy', 'estimated_changed_lines',
          'context_overlay', 'execution', 'add_tests', 'add_coverage', 'add_acceptance'}


def restore(root, prefixes, packet, fields):
    """Validate the evidence binding and assemble only explicitly supplied task changes."""
    if packet['project'] != str(root.resolve()) or packet['current_snapshot'] != scan(root, prefixes)['snapshot']:
        raise ValueError('Failure evidence became stale or belongs to another project')
    if not isinstance(fields, dict) or set(fields) - FIELDS - {'failure_analysis', 'architecture_replacements', 'strategy_review', 'recovery_decision'}:
        raise ValueError('Recovery accepts flat failed-task changes, not tasks, IDs or a replacement plan')
    analysis = fields.get('failure_analysis')
    if not isinstance(analysis, str) or len(analysis.strip()) < 40:
        raise ValueError('Explain failure evidence, cause, corrective approach and validation in failure_analysis')
    from strategy_review import validate as validate_strategy
    strategy = validate_strategy(packet, fields)
    from recovery_protocol import validate as validate_decision
    decision = validate_decision(fields.get('recovery_decision'), packet, action='repair')
    original = json.loads(Path(packet['plan']).read_text())
    if original.get('project') != str(root.resolve()):
        raise ValueError('Original plan belongs to another project')
    if packet.get('recovery_plan_sha256') and digest(original) != packet['recovery_plan_sha256']:
        raise ValueError('Original plan changed since the recovery session was bound')
    remaining = packet['remaining']
    failed = packet['failed_todo']['id']
    selected = [task for task in remaining if task['id'] == failed]
    if len(selected) != 1 or selected[0] != packet['failed_todo']:
        raise ValueError('Failure packet does not identify one exact remaining contract')
    originals = {task['id']: task for task in original['tasks']}
    if any({key: value for key, value in originals.get(task['id'], {}).items() if key != 'baseline'} != task
           for task in remaining):
        raise ValueError('Remaining plan contracts changed since the failure evidence')
    plan = copy.deepcopy(original)
    plan['tasks'] = copy.deepcopy(remaining)
    completed = {task['id'] for task in packet['completed']}
    for task in plan['tasks']:
        task['depends_on'] = [dep for dep in task.get('depends_on', []) if dep not in completed]
    patch = {'task_updates': [{'id': failed, **{key: value for key, value in fields.items() if key in FIELDS}}]}
    if 'architecture_replacements' in fields:
        patch['architecture_replacements'] = fields['architecture_replacements']
    result = apply(plan, patch)
    result.pop('draft_repair', None)
    # This review supersedes the old operational launch instruction. Its original
    # receipt stays on the parent plan; it is not a retry of that historical todo.
    result.pop('operational_retry', None)
    result['failure_analysis'] = analysis
    if decision is not None:
        result['recovery_decision'] = decision
    if strategy is not None:
        next(task for task in result['tasks'] if task['id'] == failed)['repair_strategy_review'] = strategy
    result['recovery_patch'] = {'todo': failed, 'evidence_sha256': digest(packet),
        'fields': sorted(set(fields) - {'failure_analysis'}),
        'method': 'Model-authored failed-task patch; Python preserves remaining contracts'}
    return result
