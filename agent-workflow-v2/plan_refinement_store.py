"""Assemble small model-authored updates without generating or repairing their content."""
import copy
import json
import re
from pathlib import Path
from plan_draft import checked_binding, digest
from plans import validate_task

CHANGES = {'estimated_changed_lines','steps','test_strategy','assumptions','context_overlay',
           'execution','criterion_replacements','add_files','add_tests','add_coverage','add_acceptance'}
CHILD_FIELDS = {'id','goal','steps','assumptions','test_strategy','estimated_changed_lines',
                'files','tests','acceptance','coverage','context','execution','depends_on','inspect'}


def child_directory(bound_path):
    """Keep immutable receipts outside the project and scoped to this binding file."""
    path = Path(bound_path).resolve()
    return path.parent / (path.name + '.children')


def binding_id(bound_path, bound):
    """Prevent replay from another session even when it reviewed the same draft."""
    return digest({'path':str(Path(bound_path).resolve()), 'binding':bound})


def validate_child(root, child):
    """Run all per-task gates; cross-child preservation and topology wait for commit."""
    if not isinstance(child, dict) or set(child)-CHILD_FIELDS:
        raise ValueError('A staged child accepts only full task contract fields')
    if not isinstance(child.get('id'), str) or not child['id'].strip():
        raise ValueError('A child needs a nonempty id')
    deps = child.get('depends_on')
    if not isinstance(deps, list) or not all(isinstance(x,str) and x for x in deps):
        raise ValueError('A child needs depends_on as an array of IDs')
    validate_task(root, child, 3)


def stage(root, prefixes, bound_path, child):
    """Validate and durably stage ONE child; never publish a plan or modify source."""
    bound = checked_binding(root, prefixes, bound_path)
    if not bound.get('refine_task') or bound.get('coverage_review'):
        raise ValueError('Child staging requires a selected task refinement')
    validate_child(root, child)
    record = {'binding':binding_id(bound_path,bound), 'task':copy.deepcopy(child)}
    receipt = digest(record)
    folder = child_directory(bound_path)
    if folder.is_relative_to(root.resolve()):
        raise ValueError('Child receipts must stay outside the project')
    folder.mkdir(exist_ok=True)
    path = folder / (receipt+'.json')
    try:
        with path.open('x') as handle:
            json.dump(record,handle,ensure_ascii=False,indent=2)
    except FileExistsError:
        if json.loads(path.read_text()) != record:
            raise ValueError('Existing child receipt is corrupt')
    return {'staged':True,'id':child['id'],'child_ref':receipt,'plan_accepted':False,
            'next':'Stage remaining children; then plan_store child_refs in dependency order. Staging is not plan acceptance.'}


def load_children(bound_path, bound, refs):
    """Load exactly the selected immutable versions; reject stale, missing or edited data."""
    if not isinstance(refs,list) or not 2<=len(refs)<=4 or any(
            not isinstance(ref,str) or not re.fullmatch('[a-f0-9]{64}',ref) for ref in refs):
        raise ValueError('child_refs requires 2-4 receipts returned by plan_child_store')
    if len(set(refs)) != len(refs):
        raise ValueError('Duplicate child receipts')
    children = []
    for ref in refs:
        path = child_directory(bound_path)/(ref+'.json')
        if not path.is_file():
            raise ValueError('Missing staged child receipt: '+ref)
        record = json.loads(path.read_text())
        if digest(record)!=ref or record.get('binding')!=binding_id(bound_path,bound):
            raise ValueError('Child receipt is corrupt or belongs to another draft/session')
        validate_child(Path(bound['project']),record['task'])
        children.append(copy.deepcopy(record['task']))
    return children


def assemble(bound_path, bound, fields):
    """Inject the pinned task ID and package exact typed values for existing native gates."""
    if not isinstance(fields,dict):
        raise ValueError('Refinement fields must be an object')
    if 'task_updates' in fields:
        return copy.deepcopy(fields)  # Older native artifacts retain their existing strict guard.
    unknown = set(fields)-CHANGES-{'child_refs','unchanged','architecture_replacements'}
    if unknown or not fields:
        raise ValueError('Use flat refinement fields; unknown fields: '+', '.join(sorted(unknown)))
    update = {'id':bound['refine_task']}
    if 'unchanged' in fields:
        if fields != {'unchanged':True}:
            raise ValueError('unchanged must be true and cannot accompany edits')
    elif 'child_refs' in fields:
        if set(fields)-{'child_refs','architecture_replacements'}:
            raise ValueError('Commit a split with child_refs only, plus optional architecture_replacements')
        update['replace_with'] = load_children(bound_path,bound,fields['child_refs'])
    else:
        update.update({key:copy.deepcopy(value) for key,value in fields.items() if key in CHANGES})
    result = {'task_updates':[update]}
    if 'architecture_replacements' in fields:
        result['architecture_replacements'] = copy.deepcopy(fields['architecture_replacements'])
    return result
