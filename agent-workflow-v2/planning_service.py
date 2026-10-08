"""Create plans with subscription ChatGPT or local Qwen, using one shared contract."""
import copy
import json
from pathlib import Path
from project_map import scan
import tasks
from runner_process import BASE, invoke, read, save


def create(project, request, output, planner='chatgpt', timeout=600, handoff=None, *,
           clarifier='auto', researcher='auto', answers=None, interactive=False, refresh=False, draft_plan=None,refiner=None,review_draft=None):
    """New plans need draft plus task refinement; executed recovery retains frozen contracts."""
    options=dict(clarifier=clarifier,researcher=researcher,answers=answers,interactive=interactive,
                 refresh=refresh,draft_plan=draft_plan)
    if review_draft and (handoff or draft_plan):raise ValueError('Choose review-draft or draft repair, not both')
    if handoff:return create_draft(project,request,output,planner,timeout,handoff,**options)
    from staged_planning import create as staged
    if review_draft:
        from staged_planning import adopt
        return staged(project,request,output,planner,timeout,adopt,{'source':review_draft},refiner)
    return staged(project,request,output,planner,timeout,create_draft,options,refiner)


def create_draft(project, request, output, planner='chatgpt', timeout=600, handoff=None, *,
           clarifier='auto', researcher='auto', answers=None, interactive=False, refresh=False, draft_plan=None,require_refinement=False):
    """Generate a new external plan; planning never invokes the todo executor."""
    project, output = project.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(project):
        raise ValueError('Choose a new plan path outside the project')
    if planner not in ('chatgpt', 'qwen'):
        raise ValueError('Planner must be chatgpt or qwen')
    lineage = None
    if handoff and draft_plan:
        raise ValueError('Accepted-run replanning and unaccepted draft repair are separate')
    if handoff:
        packet = json.loads(handoff.read_text())
        if Path(packet['project']).resolve() != project or packet['current_snapshot'] != scan(project, ['.'])['snapshot']:
            raise ValueError('Replanning evidence belongs to another project or is stale')
        from failure_refresh import refresh as refresh_diagnostics
        packet = refresh_diagnostics(packet)
        from strategy_review import POLICY
        packet['strategy_review_policy'] = dict(POLICY)
        from recovery_protocol import POLICY as RECOVERY_POLICY
        packet['failure_recovery_policy'] = dict(RECOVERY_POLICY)
        # Historical packets can predate a reporter fix. Keep them immutable and
        # pin the newly extracted observations separately for this review.
        output.parent.mkdir(parents=True, exist_ok=True)
        handoff = output.with_suffix('.evidence.json')
        if handoff.exists():
            raise ValueError('Choose a new plan path; this review already has pinned evidence')
        save(handoff, packet)
        from failure_context import build
        request,selection=build(project,packet,planner)
        request += '\nRECOVERY MODE: submit failure_analysis, strategy_review and changed steps for the failed todo via plan_store. Begin steps with the exact strategy_review.first_check. Include recovery_decision(action=repair); use recovery_report for escalation. Python preserves every untouched contract, acceptance case and test command. Do not reproduce the full plan.'
        lineage = packet
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline = None
    if not handoff and not draft_plan:
        from request_pipeline import prepare
        pipeline = prepare(project, request, output, planner, timeout, clarifier, researcher,
                           answers, interactive, refresh)
        if not pipeline['passed']:
            return pipeline
        request = pipeline['refined_prompt']
    request_path = output.with_suffix('.request.txt')
    request_path.write_text(request)
    if handoff:save(output.with_suffix('.context.json'),selection)
    command = [str(BASE / 'qwen-agent'), '--profile', 'chatgpt-quality' if planner == 'chatgpt' else 'mtplx-quality',
        '--project', str(project), '--role', 'architect', '--batch', '--json', '--quiet',
        '--plan', str(output), '--prompt-file', str(request_path)]
    if require_refinement:command.append('--require-refinement')
    if handoff:
        from planning_limits import arguments
        command+=['--replan-evidence',str(handoff.resolve()),*arguments(planner,'recovery')]
    if draft_plan:
        command += ['--plan-draft', str(draft_plan.resolve()), '--context','65536',
                    '--input-tokens','24576','--output-tokens','8192']
        if planner == 'qwen':
            command += ['--reasoning-budget','1024']
    result = invoke(command, output.with_suffix('.planning'), timeout)
    from run_metrics import collect
    result['metrics'] = collect(result, output.with_suffix('.planning'))
    result.update(planner=planner, plan=str(output))
    if handoff and result.get('session'):
        from recovery_report import verified as recovery_report
        report = recovery_report(result['session'])
        if report:
            result['recovery_decision'] = report['decision']
    if pipeline:
        result['pipeline'] = pipeline
    if result['exit_code'] == 0 and output.exists():
        from plan_runner import validate
        plan = json.loads(output.read_text())
        try:
            validate(project, plan)
            if lineage:
                attach_lineage(plan, lineage)
                plan['replan_validation'] = {'passed': True}
                save(output, plan)
            result['passed'] = True
        except ValueError as error:
            plan['replan_validation'] = {'passed': False, 'reason': str(error)}
            save(output, plan)
            result.update(passed=False, validation_error=str(error))
    else:
        result['passed'] = False
    save(output.with_suffix('.planning-result.json'), result)
    return result


def attach_lineage(plan, packet):
    """Reject scope expansion or weakened acceptance when repairing a failed plan."""
    remaining = packet['remaining']
    for path, digest in packet.get('acceptance_fixtures', {}).items():
        if tasks.hash_file(Path(path)) != digest:
            raise ValueError('An immutable fixture changed since planning')
    allowed_files = {p for t in remaining for p in t['files']}
    proposed_files = {p for t in plan['tasks'] for p in t['files']}
    if not proposed_files <= allowed_files:
        raise ValueError('Replan expands file scope; requires an explicitly revised user request')
    old_cases = {json.dumps(case, sort_keys=True) for t in remaining for case in t['acceptance']}
    new_cases = {json.dumps(case, sort_keys=True) for t in plan['tasks'] for case in t['acceptance']}
    old_tests = {tuple(argv) for t in remaining for argv in t['tests']}
    new_tests = {tuple(argv) for t in plan['tasks'] for argv in t['tests']}
    if not old_cases <= new_cases or not old_tests <= new_tests:
        raise ValueError('Replan dropped frozen acceptance or test commands')
    # Re-check immutable fixtures against the failed local baseline before executing.
    if packet.get('session'):
        frozen = read(Path(packet['session']) / 'task-state.json')
        for path, digest in frozen.get('readonly_tests', {}).items():
            if tasks.hash_file(Path(path)) != digest:
                raise ValueError('An immutable fixture changed since failure')
        # An unfinished identical atomic contract keeps its original source baseline.
        # Failed oversized functions must not become grandfathered legacy code.
        original=frozen.get('task',{})
        for todo in plan['tasks']:
            if (set(todo['files'])==set(original.get('files',[]))
                and {tuple(argv) for argv in todo['tests']}=={tuple(argv) for argv in original.get('tests',[])}
                and {json.dumps(case,sort_keys=True) for case in todo['acceptance']}==
                    {json.dumps(case,sort_keys=True) for case in original.get('acceptance',[])}):
                todo['baseline']=str(Path(packet['session'])/'task-state.json')
    plan['replan_lineage'] = {'parent_plan': packet['plan'], 'reason': packet['reason'],
                            'completed': copy.deepcopy(packet['completed']),
                            'snapshot': packet['current_snapshot']}
