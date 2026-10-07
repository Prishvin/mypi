"""Validate model-authored coverage decisions without asking a model to check bookkeeping."""
import copy
import json

LEVELS={'unit','integration','e2e'}


def nonempty(value):
    """Keep case descriptions and pass/fail oracles explicit."""
    return isinstance(value,str) and bool(value.strip())


def validate(draft, coverage):
    """Require all existing cases, traceable requirements, valid owners and observable gaps."""
    if not isinstance(coverage,dict) or set(coverage)!={'strategy','checks','requirements','gaps'}:
        raise ValueError('coverage_plan needs strategy, checks, requirements and gaps')
    if len(json.dumps(coverage).encode())>131072:raise ValueError('Keep coverage planning below 128 KiB')
    strategy=coverage['strategy']
    if not isinstance(strategy,dict) or set(strategy)!=LEVELS or not all(nonempty(x) for x in strategy.values()):
        raise ValueError('Explain unit, integration and e2e strategy; explicitly justify any not applicable layer')
    tasks={t['id']:t for t in draft['tasks']}
    expected={(t['id'],c['id']) for t in tasks.values() for c in t['acceptance']}
    observed=set()
    if not isinstance(coverage['checks'],list):raise ValueError('Coverage checks must be an array')
    for row in coverage['checks']:
        if not isinstance(row,dict) or set(row)!={'task','criterion','level','test','oracle'}:
            raise ValueError('Each check needs task, criterion, level, test index and oracle')
        key=(row['task'],row['criterion'])
        if key not in expected or row['level'] not in LEVELS or not nonempty(row['oracle']):
            raise ValueError('Coverage check references an unknown case/level or lacks an observable oracle')
        tests=tasks[row['task']]['tests'];index=row['test']
        if type(index) is not int or not 0<=index<len(tests):raise ValueError('Coverage test index is invalid')
        if {'criterion':row['criterion'],'test':index} not in tasks[row['task']]['coverage']:
            raise ValueError('Coverage check must reference the draft case-to-command mapping')
        observed.add(key)
    if observed!=expected:raise ValueError('Coverage review must include every original acceptance case')
    if not isinstance(coverage['gaps'],list):raise ValueError('Coverage gaps must be an array')
    gaps=set()
    for gap in coverage['gaps']:
        if not isinstance(gap,dict) or set(gap)!={'task','case','level','test','reason'}:
            raise ValueError('Gap needs owner task, full case, level, test argv and reason')
        case=gap['case'];owner=gap['task']
        if not isinstance(case,dict) or set(case)!={'id','given','when','then'} or not all(nonempty(x) for x in case.values()):
            raise ValueError('Coverage gap needs observable id/given/when/then')
        key=(owner,case['id'])
        if owner not in tasks or key in expected|gaps or gap['level'] not in LEVELS or not nonempty(gap['reason']):
            raise ValueError('Coverage gap needs a known owner and a unique new case')
        if not isinstance(gap['test'],list) or not gap['test'] or not all(nonempty(x) for x in gap['test']):
            raise ValueError('Coverage gap requires a runnable test argv')
        gaps.add(key)
    requirements=coverage['requirements'];linked=set()
    if not isinstance(requirements,list) or not requirements:raise ValueError('Map request requirements to checks')
    for item in requirements:
        if not isinstance(item,dict) or set(item)!={'requirement','cases'} or not nonempty(item['requirement']) or not item['cases']:
            raise ValueError('Each requirement needs a description and case references')
        for ref in item['cases']:
            if not isinstance(ref,dict) or set(ref)!={'task','criterion'}:raise ValueError('Requirement references need task and criterion')
            key=(ref['task'],ref['criterion'])
            if key not in expected|gaps:raise ValueError('Requirement points to an unknown check')
            linked.add(key)
    if linked!=expected|gaps:raise ValueError('Every planned check and gap must link to a request requirement')


def annotate(draft, patch):
    """Attach coverage only; preserve all original architecture and task contracts."""
    if not isinstance(patch,dict) or set(patch)!={'coverage_plan'}:raise ValueError('Coverage review accepts only coverage_plan')
    validate(draft,patch['coverage_plan'])
    return {**copy.deepcopy(draft),'coverage_plan':copy.deepcopy(patch['coverage_plan'])}


def require_gaps(tasks, gaps, owner=None):
    """A reviewed task or its split children must incorporate assigned missing coverage."""
    for gap in gaps:
        if owner is not None and gap['task']!=owner:continue
        matches=[t for t in tasks if gap['case'] in t['acceptance'] and gap['test'] in t['tests']]
        if not any({'criterion':gap['case']['id'],'test':t['tests'].index(gap['test'])} in t['coverage'] for t in matches):
            raise ValueError('Refinement must incorporate coverage gap '+gap['task']+'/'+gap['case']['id'])
