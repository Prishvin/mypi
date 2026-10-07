"""Propose and explicitly approve corrections to an unfinished generated contract."""
import copy
import json
import time
from pathlib import Path
from plan_draft import digest
from project_map import scan
from runner_process import read, save


def bound_packet(root, evidence):
    """Bind revision to unchanged failure evidence, original plan and project."""
    packet = read(evidence)
    if packet.get('project') != str(root.resolve()) or packet.get('current_snapshot') != scan(root, ['.'])['snapshot']:
        raise ValueError('Revision evidence belongs to another project or is stale')
    original = read(Path(packet['plan']))
    from plan_runner import validate
    validate(root, original)
    target = packet['failed_todo']['id']
    tasks = {t['id']: t for t in original['tasks']}
    for task in packet['remaining']:
        if {k: v for k, v in tasks.get(task['id'], {}).items() if k != 'baseline'} != task:
            raise ValueError('Original plan differs from revision evidence')
    if target not in tasks or tasks[target].get('status') == 'done' or any(t['id'] == target for t in packet['completed']):
        raise ValueError('Revision may only target an unfinished todo')
    return packet, original


def prepare(root, evidence, folder, reason):
    """Make an isolated non-executable draft; retain accepted work in bound evidence."""
    root, evidence, folder = root.resolve(), evidence.resolve(), folder.resolve()
    if len(reason.strip()) < 20:
        raise ValueError('Explain why a contract revision is requested')
    if folder.exists() or folder.is_relative_to(root):
        raise ValueError('Use a new revision folder outside the project')
    packet, original = bound_packet(root, evidence)
    draft = copy.deepcopy(original)
    for key in ('replan_lineage', 'replan_validation', 'recovery_patch', 'failure_analysis', 'operational_retry', 'draft_repair'):
        draft.pop(key, None)
    draft['tasks'] = copy.deepcopy(packet['remaining'])
    completed = {t['id'] for t in packet['completed']}
    for task in draft['tasks']:
        for key in ('baseline', 'evidence', 'result', 'shadow_snapshot'):
            task.pop(key, None)
        task['status'] = 'todo'
        task['depends_on'] = [dep for dep in task.get('depends_on', []) if dep not in completed]
    binding = {'project': str(root), 'evidence': str(evidence), 'evidence_sha256': digest(packet),
        'parent_plan_sha256': digest(original), 'target': packet['failed_todo']['id'],
        'snapshot': packet['current_snapshot'], 'reason': reason, 'created_epoch': time.time()}
    draft['contract_revision'] = {'status': 'proposed', 'binding': str(folder/'binding.json')}
    from tasks import readonly_tests
    draft['acceptance_fixtures'] = readonly_tests(root, [argv for task in draft['tasks'] for argv in task['tests']])
    binding['draft_sha256'] = digest(draft)
    folder.mkdir(parents=True)
    save(folder/'binding.json', binding)
    save(folder/'draft.json', draft)
    return binding, packet, draft


def inspect(root, proposal):
    """Require exact unrelated contracts and explicit model-authored criterion corrections."""
    proposal = proposal.resolve()
    plan = read(proposal)
    marker = plan.get('contract_revision', {})
    if marker.get('status') != 'proposed':
        raise ValueError('Expected an unapproved revision proposal')
    folder = proposal.parent
    if marker.get('binding') != str(folder/'binding.json'):
        raise ValueError('Revision binding path differs')
    binding, draft = read(folder/'binding.json'), read(folder/'draft.json')
    if binding.get('draft_sha256') != digest(draft):
        raise ValueError('Pinned revision draft changed')
    packet, original = bound_packet(root, Path(binding['evidence']))
    if (binding['project'] != str(root.resolve()) or binding['evidence_sha256'] != digest(packet)
            or binding['parent_plan_sha256'] != digest(original) or binding['snapshot'] != packet['current_snapshot']):
        raise ValueError('Revision binding changed')
    if any(plan.get(key) != draft.get(key) for key in ('goal', 'architecture', 'acceptance_fixtures')):
        raise ValueError('Revision changed project goal, architecture or immutable fixtures')
    before, after = draft['tasks'], plan['tasks']
    if [t['id'] for t in before] != [t['id'] for t in after]:
        raise ValueError('Revision cannot add, split or remove todos')
    target = binding['target']
    for old, new in zip(before, after):
        if old['id'] != target:
            if new != old:
                raise ValueError('Revision changed an unrelated todo')
        else:
            for key in ('id', 'goal', 'files', 'depends_on', 'tests', 'coverage'):
                if old.get(key) != new.get(key):
                    raise ValueError('Revision changed protected field: '+key)
    corrections = plan.get('draft_repair', {}).get('criterion_corrections', [])
    old = next(t for t in before if t['id'] == target)
    new = next(t for t in after if t['id'] == target)
    revised = copy.deepcopy(old['acceptance'])
    seen = set()
    for correction in corrections:
        if correction.get('todo') != target or len(correction.get('reason', '').strip()) < 16:
            raise ValueError('Each correction needs the selected todo and evidence reason')
        a, b = correction['old'], correction['new']
        if a == b or a['id'] != b['id'] or a['id'] in seen or revised.count(a) != 1:
            raise ValueError('Correction must match one exact old criterion with the same ID')
        if not all(isinstance(b.get(k), str) and b[k].strip() for k in ('id', 'given', 'when', 'then')):
            raise ValueError('Corrected criterion needs complete given/when/then')
        seen.add(a['id']); revised[revised.index(a)] = copy.deepcopy(b)
    if not corrections or new['acceptance'] != revised:
        raise ValueError('Every acceptance change needs an explicit exact correction record')
    from plan_runner import validate
    validate(root, plan)
    return plan, packet, binding, corrections


def propose(root, evidence, folder, reason, planner='qwen', timeout=1800):
    """Ask the selected planner for a proposal only, never start an executor."""
    from project_lock import exclusive
    from runner_process import BASE
    root, folder = root.resolve(), folder.resolve()
    with exclusive(root, BASE):
        binding, packet, draft = prepare(root, evidence, folder, reason)
        from plan_refinement import packet_data, bounded_prompt, invoke_review
        from failure_test_context import collect
        data = packet_data(reason, draft, binding['target'])
        data['observed_failure'] = {'reason': packet['reason'], 'failed_tests': packet['failed_tests'],
                                   'selected_tests': collect(root, packet)}
        prompt = bounded_prompt('contract-revision', data, planner)
        output = folder/'proposal.json'
        result = invoke_review(root, folder/'draft.json', output, planner, timeout, prompt,
                               ['--refine-task', binding['target']], binding['target'], phase='recovery')
        if result['passed']:
            _, _, _, corrections = inspect(root, output)
            result.update(requires_approval=True, proposal_sha256=digest(read(output)), corrections=corrections)
            save(folder/'proposal-review.json', result)
        return result


def approve(root, proposal, output, proposal_sha256, reason):
    """Publish a separately approved plan with exact revision audit and accepted lineage."""
    from project_lock import exclusive
    from runner_process import BASE
    root, proposal, output = root.resolve(), proposal.resolve(), output.resolve()
    with exclusive(root, BASE):
        if output.exists() or output.is_relative_to(root) or len(reason.strip()) < 20:
            raise ValueError('Use a new external output and explain explicit approval')
        if digest(read(proposal)) != proposal_sha256:
            raise ValueError('Proposal differs from the reviewed digest')
        plan, packet, binding, corrections = inspect(root, proposal)
        # Only these exact, explicitly approved cases replace the old preservation
        # baseline. Original evidence is immutable and both values stay in the receipt.
        authorized = copy.deepcopy(packet)
        selected = next(t for t in plan['tasks'] if t['id'] == binding['target'])
        next(t for t in authorized['remaining'] if t['id'] == binding['target'])['acceptance'] = copy.deepcopy(selected['acceptance'])
        from planning_service import attach_lineage
        attach_lineage(plan, authorized)
        if packet.get('session'):
            selected['baseline'] = str(Path(packet['session'])/'task-state.json')
        plan['contract_revision'] = {'status': 'approved', 'proposal': str(proposal),
            'proposal_sha256': proposal_sha256, 'binding': binding, 'corrections': corrections,
            'approval_reason': reason, 'approved_epoch': time.time()}
        plan['replan_validation'] = {'passed': True, 'method': 'Explicit approved contract revision; all other preservation checks retained'}
        from plan_runner import validate
        from plans import require_review
        validate(root, plan); require_review(plan)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x') as stream:
            json.dump(plan, stream, indent=2)
        return {'plan': str(output), 'corrections': corrections, 'execution_started': False}
