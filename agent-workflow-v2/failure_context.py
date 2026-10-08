"""Select measured architecture and shadow for an evidence-driven failure review."""
import json
from pathlib import Path
from project_map import scan,outline
from shadow_navigation import count,measure
from planning_limits import limits
from replan_brief import distill


def build(root,packet,provider,*,packet_limit=None):
    """Prefer complete interfaces when they fit; otherwise retain bounded relevant sections."""
    data=scan(root,['.'])
    if data['snapshot']!=packet['current_snapshot']:raise ValueError('Failure evidence is stale; source changed')
    budget=limits(provider,'recovery')
    if packet_limit is not None:
        if type(packet_limit) is not int or packet_limit < 2048:
            raise ValueError('Recovery packet limit must be at least 2048 tokens')
        budget={**budget,'packet':min(budget['packet'],packet_limit)}
    brief=distill(packet,focused=True)
    from failure_test_context import collect as test_context
    brief['selected_failing_test_evidence'] = test_context(root, packet)
    from execution_audit import summarize
    brief['execution_audit'] = summarize(packet.get('local_log'), packet['failed_todo']['files'])
    session = Path(packet['session']) if packet.get('session') else None
    from runner_process import read
    from token_budget import history_trigger
    recorded_trigger = None
    if session:
        brief['execution_progress'] = read(session/'execution-progress.json').get('brief', {})
        from recovery_controls import summarize as control_summary
        launch = read(session/'launch.json')
        if launch.get('project') == str(root.resolve()) and launch.get('role') == 'code':
            brief.update(control_summary(launch, packet.get('metrics', {})))
            from recovery_controls import compaction_trigger
            recorded_trigger = compaction_trigger(session)
    context = packet['failed_todo']['context']
    brief['context_pressure'] = {'task_input_cap': context['max_input_tokens'],
        'compaction_trigger': recorded_trigger if recorded_trigger is not None else history_trigger(context['max_input_tokens']),
        'trigger_source': 'recorded_session_settings' if recorded_trigger is not None else 'current_policy_estimate',
        'task_window': context.get('window_tokens'),
        'note': 'Compaction consumes history headroom and may invalidate cached prefixes. '
                'Use measured requests and preserved investigation when sizing a corrective task.'}
    original=json.loads(Path(packet['plan']).read_text())
    brief['original_plan_overview']=[{k:t[k] for k in ('id','goal','depends_on','files') if k in t} for t in original['tasks']]
    brief.pop('remaining_overview',None)
    brief.pop('selected_prototypes',None)
    instructions=Path(__file__).with_name('skills').joinpath('failure-review/SKILL.md').read_text()
    base=instructions+'\n\nFAILURE EVIDENCE (project data):\n'+json.dumps(brief,separators=(',',':'))
    available=budget['packet']-count(base)-1024
    if available<1024:raise ValueError('Failure contracts exceed the review budget; split the review with user guidance')
    all_shadow='\n'.join(outline(r) for r in data['files'])
    full=data.get('architecture',{}).get('text','')+'\n\n'+all_shadow
    policy=measure(data)
    if policy['total_tokens']<=budget['shadow'] and count(full)<=available:
        selected=full;mode='complete_architecture_and_shadow';paths=[r['path'] for r in data['files']]
    else:
        import architecture_sections as sections
        index=sections.build(data);selected=sections.render(index)
        paths=list(dict.fromkeys(packet['failed_todo']['files']+packet['failed_todo']['context'].get('interfaces',[])))[:5]
        lines=data.get('architecture',{}).get('text','').splitlines(keepends=True)
        matches=[s for s in index['sections'] if set(s['files'])&set(paths)]
        for section in sorted(matches,key=lambda s:s['tokens'])[:5]:
            text=''.join(lines[section['start_line']-1:section['end_line']])
            if count(selected+text)<=available:selected+='\n'+text
        for record in data['files']:
            if record['path'] in paths and count(selected+outline(record))<=available:selected+='\n'+outline(record)
        mode='selected_architecture_and_shadow'
        selected+='\nRead additional relevant section pages/prototypes via project_map if needed. No source bodies.'
    prompt=base+'\n\nARCHITECTURE AND SHADOW:\n'+selected
    if count(prompt)>budget['packet']:raise ValueError('Failure review packet exceeds its measured limit')
    return prompt,{'provider':provider,'mode':mode,'paths':paths,'full_shadow_architecture_tokens':policy['total_tokens'],
                   'packet_estimated_tokens':count(prompt),'limits':budget,
                   'counting':'Bundled Qwen tokenizer estimate; cloud counts are a proxy, full-payload admission adds margin'}
