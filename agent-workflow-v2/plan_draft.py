"""Repair unaccepted model proposals with small patches and native preservation checks."""
import copy
import hashlib
import json
from pathlib import Path
from project_map import scan


def unique_pairs(pairs):
    """Reject duplicate JSON keys rather than choosing a hidden conflicting value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate serialized patch key: ' + key)
        result[key] = value
    return result


def decode(patch):
    """Decode exact JSON data from legacy parameter serialization, without inventing fields."""
    result = copy.deepcopy(patch)
    notes = []
    for field in ('task_updates', 'architecture_replacements'):
        value = result.get(field)
        if not isinstance(value, str):
            continue
        if len(value.encode()) > 1048576:
            raise ValueError('Serialized patch exceeds 1 MiB')
        try:
            parsed = json.loads(value, object_pairs_hook=unique_pairs)
        except json.JSONDecodeError:
            # Some XML adapters join later JSON parameters into the first parameter string.
            parsed = json.loads('{"' + field + '":' + value + '}', object_pairs_hook=unique_pairs)
            if not isinstance(parsed, dict) or set(parsed) - {field, 'architecture_replacements'}:
                raise ValueError('Ambiguous serialized patch parameters')
            if (set(parsed) - {field}).intersection(result):
                raise ValueError('Conflicting serialized and outer patch fields')
            result.update(parsed)
        else:
            result[field] = parsed
        notes.append('Decoded literal JSON ' + field + '; no contract data changed')
    return result, notes


def split_data(update):
    """Normalize explicit overlays and reject conflicting aggregate split metadata."""
    allowed = {'id', 'replace_with', 'estimated_changed_lines', 'execution', 'context_overlay'}
    if set(update) - allowed or not update['replace_with']:
        raise ValueError('A split needs nonempty replace_with and only unambiguous metadata')
    replacements = copy.deepcopy(update['replace_with'])
    if 'estimated_changed_lines' in update and update['estimated_changed_lines'] != sum(
            item.get('estimated_changed_lines', 0) for item in replacements):
        raise ValueError('Aggregate split estimate conflicts with child estimates')
    for item in replacements:
        overlay = item.pop('context_overlay', {})
        item['context'] = {**item.get('context', {}), **overlay}
        if 'execution' in update and item.get('execution') != update['execution']:
            raise ValueError('Aggregate split execution conflicts with child policies')
        for key, value in update.get('context_overlay', {}).items():
            if item['context'].get(key) != value:
                raise ValueError('Aggregate split context conflicts with child context')
    return replacements


def digest(value):
    """Hash canonical draft data independently of pretty-printing."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def bind(root, source, destination, snapshot, target=None, coverage=False):
    """Pin only an unaccepted external proposal; accepted execution uses replanning."""
    source = source.resolve()
    if source.is_relative_to(root.resolve()) or source.stat().st_size > 1048576:
        raise ValueError('Keep a bounded proposal outside the source project')
    proposal = json.loads(source.read_text())
    if proposal.get('plan_version') != 3 or not proposal.get('tasks') or not proposal.get('architecture'):
        raise ValueError('Draft repair requires a complete unaccepted V3 proposal')
    if proposal.get('project') and Path(proposal['project']).resolve() != root.resolve():
        raise ValueError('Draft belongs to another project')
    if proposal.get('replan_lineage') or any(t.get('status') == 'done' or t.get('evidence') or
            t.get('baseline') for t in proposal['tasks']):
        raise ValueError('Accepted work requires evidence-bound replan, not draft repair')
    bound = {'project': str(root.resolve()), 'snapshot': snapshot, 'proposal': proposal,
             'source': str(source), 'proposal_sha256': digest(proposal)}
    if coverage:
        if target:raise ValueError('Coverage review and task refinement are separate calls')
        bound['coverage_review']=True
    if target is not None:
        if target not in {t['id'] for t in proposal['tasks']}:raise ValueError('Unknown refinement target')
        bound['refine_task']=target
    destination.write_text(json.dumps(bound, indent=2))
    return str(destination)


def preserved(original, replacement):
    """Retain all old files, observable cases and test commands during a split."""
    cases = {json.dumps(c, sort_keys=True) for c in original['acceptance']}
    new_cases = {json.dumps(c, sort_keys=True) for t in replacement for c in t['acceptance']}
    tests = {tuple(a) for a in original['tests']}
    new_tests = {tuple(a) for t in replacement for a in t['tests']}
    files = set(original['files'])
    new_files = {p for t in replacement for p in t['files']}
    if not cases <= new_cases or not tests <= new_tests or not files <= new_files:
        raise ValueError('Draft repair dropped an original case, test command or file')
    if original['id'] not in {t['id'] for t in replacement}:
        raise ValueError('Keep the original todo ID in a split to preserve later dependencies')


def update_task(task, update):
    """Apply explicit metadata or additive test changes without weakening acceptance."""
    allowed = {'id','estimated_changed_lines','steps','test_strategy','assumptions','context_overlay',
               'execution','add_files','add_tests','add_coverage','add_acceptance','replace_with','criterion_replacements'}
    if set(update) - allowed:
        raise ValueError('Unknown draft task patch fields')
    if 'replace_with' in update:
        replacement = split_data(update)
        preserved(task, replacement)
        return replacement
    result = copy.deepcopy(task)
    corrected = copy.deepcopy(task)
    for edit in update.get('criterion_replacements', []):
        if set(edit) != {'old','new','reason'} or len(edit['reason']) < 16 or edit['old']['id'] != edit['new']['id']:
            raise ValueError('Explicit unaccepted criterion corrections need matching IDs and an evidence reason')
        matches = [i for i, case in enumerate(corrected['acceptance']) if case == edit['old']]
        if len(matches) != 1 or not all(edit['new'].get(k) for k in ('id','given','when','then')):
            raise ValueError('Criterion correction must match one exact old case')
        corrected['acceptance'][matches[0]] = copy.deepcopy(edit['new'])
    result['acceptance'] = corrected['acceptance']
    for key in ('estimated_changed_lines','steps','test_strategy','assumptions','execution'):
        if key in update:
            result[key] = copy.deepcopy(update[key])
    if 'context_overlay' in update:
        result['context'] = {**result.get('context', {}), **copy.deepcopy(update['context_overlay'])}
    for patch_key, key in [('add_files','files'),('add_tests','tests'),('add_coverage','coverage'),('add_acceptance','acceptance')]:
        for item in update.get(patch_key, []):
            if item not in result[key]:
                result[key].append(copy.deepcopy(item))
    preserved(corrected, [result])
    return [result]


def apply(proposal, patch):
    """Merge sparse model-authored corrections; ordinary V3 validation still decides acceptance."""
    patch, transport_notes = decode(patch)
    if set(patch) - {'task_updates','architecture_replacements'}:
        raise ValueError('Draft mode accepts only task_updates and architecture_replacements')
    updates = patch.get('task_updates', [])
    if not isinstance(updates, list) or not updates:
        raise ValueError('Supply nonempty task_updates')
    known = {t['id'] for t in proposal['tasks']}
    keys = [u['id'] for u in updates]
    if len(keys) != len(set(keys)) or not set(keys) <= known:
        raise ValueError('Patch IDs must be unique existing draft todos')
    result = copy.deepcopy(proposal)
    lookup = {u['id']:u for u in updates}
    result['tasks'] = [item for task in result['tasks'] for item in
                       (update_task(task, lookup[task['id']]) if task['id'] in lookup else [task])]
    all_ids = [t['id'] for t in result['tasks']]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('Split introduced duplicate todo IDs')
    for edit in patch.get('architecture_replacements', []):
        if set(edit) != {'old','new'} or not edit['old'] or not edit['new'] or result['architecture'].count(edit['old']) != 1:
            raise ValueError('Architecture replacement must match one exact nonempty passage')
        result['architecture'] = result['architecture'].replace(edit['old'], edit['new'], 1)
    result['draft_repair'] = {'proposal_sha256':digest(proposal), 'patched_todos':keys,
                            'transport_normalization':transport_notes,
                            'criterion_corrections':[{'todo':u['id'], **edit} for u in updates
                                for edit in u.get('criterion_replacements', [])],
                            'method':'Sparse model corrections; Python preserves unchanged contracts'}
    return result


def restore(root, prefixes, bound_path, patch):
    """Reject changed bindings or source before merging a model's patch."""
    bound = json.loads(Path(bound_path).read_text())
    if bound['project'] != str(root.resolve()) or bound['snapshot'] != scan(root, prefixes)['snapshot']:
        raise ValueError('Draft binding or source snapshot is stale')
    if digest(bound['proposal']) != bound['proposal_sha256']:
        raise ValueError('Pinned draft proposal hash changed')
    if bound.get('coverage_review'):
        from coverage_plan import annotate
        return annotate(bound['proposal'],patch)
    if bound.get('refine_task'):
        from plan_refinement import guard
        patch=guard(bound['proposal'],patch,bound['refine_task'])
    result=apply(bound['proposal'], patch)
    if bound.get('refine_task'):
        from coverage_plan import require_gaps
        update=patch['task_updates'][0]
        ids={t['id'] for t in update.get('replace_with',[])} or {bound['refine_task']}
        require_gaps([t for t in result['tasks'] if t['id'] in ids],
                     result.get('coverage_plan',{}).get('gaps',[]),bound['refine_task'])
    return result
