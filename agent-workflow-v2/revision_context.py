"""Select one contract and its direct producers/consumers for revision review."""
import copy


def source_paths(task):
    """Ignore shared architecture bookkeeping when linking module contracts."""
    return set(task.get('files', [])) - {'architecture.md'}


def references(task):
    """Use explicit context links, not fuzzy matches against implementation text."""
    context = task.get('context', {})
    return (set(context.get('interfaces', [])) |
            {symbol['path'] for symbol in context.get('symbols', [])}) - {'architecture.md'}


def packet_data(request, draft, target):
    """Keep global architecture/overview but omit unrelated full task contracts."""
    selected = [task for task in draft['tasks'] if task['id'] == target]
    if len(selected) != 1:
        raise ValueError('Revision context needs exactly one selected todo')
    task = selected[0]
    related = []
    for other in draft['tasks']:
        if other['id'] == target:
            continue
        if (other['id'] in task.get('depends_on', []) or target in other.get('depends_on', [])
                or source_paths(other) & references(task) or source_paths(task) & references(other)):
            related.append({key: copy.deepcopy(other[key]) for key in
                ('id', 'goal', 'files', 'depends_on', 'acceptance', 'tests', 'coverage') if key in other})
    overview = [{key: copy.deepcopy(item[key]) for key in ('id', 'goal', 'files', 'depends_on') if key in item}
                for item in draft['tasks']]
    return {'original_request': request, 'whole_plan': {'goal': draft['goal'],
                'architecture': draft['architecture'], 'tasks': overview},
            'current_task': copy.deepcopy(task), 'related_contracts': related,
            'coverage_plan': copy.deepcopy(draft.get('coverage_plan', {})),
            'selection_note': 'Complete architecture and task overview; full selected and directly related contracts only. '
                'All other exact contracts remain local and native preservation is unchanged.'}
