"""CLI shared by Pi, OpenCode and human operators."""
import argparse
import json
from pathlib import Path
from project_map import scan, write_map, select_context, render_catalog
import tasks
import retrieval
import shadow
import plans


def arguments():
    """Define the bounded navigation and validation CLI contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--prefix', action='append', default=[])
    parser.add_argument('--briefs', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    mapping = sub.add_parser('map')
    mapping.add_argument('--output', type=Path, required=True)
    catalogue = sub.add_parser('catalog')
    catalogue.add_argument('--offset', type=int, default=0)
    catalogue.add_argument('--limit', type=int, default=80)
    architecture = sub.add_parser('architecture')
    architecture.add_argument('--offset', type=int, default=0)
    architecture.add_argument('--limit', type=int, default=20)
    architecture.add_argument('--paths', nargs='*')
    architecture.add_argument('--section-offset', type=int, default=0)
    section = sub.add_parser('architecture-section')
    section.add_argument('identifier')
    section.add_argument('--sha256', required=True)
    section.add_argument('--offset', type=int, default=0)
    searching_map = sub.add_parser('architecture-search')
    searching_map.add_argument('query')
    searching_map.add_argument('--offset', type=int, default=0)
    status = sub.add_parser('architecture-status')
    status.add_argument('--shadow', type=Path, required=True)
    status.add_argument('--state', type=Path)
    rebuild = sub.add_parser('architecture-rebuild')
    rebuild.add_argument('--shadow', type=Path, required=True)
    rebuild.add_argument('--state', type=Path)
    locating = sub.add_parser('locate')
    locating.add_argument('query')
    locating.add_argument('--paths', nargs='+')
    context = sub.add_parser('context')
    context.add_argument('paths', nargs='+')
    context.add_argument('--max-bytes', type=int, default=24000)
    context.add_argument('--symbol', default='')
    refreshing = sub.add_parser('refresh')
    refreshing.add_argument('--output', type=Path, required=True)
    refreshing.add_argument('--state', type=Path)
    planning = sub.add_parser('save-plan')
    planning.add_argument('--input', type=Path, required=True)
    planning.add_argument('--output', type=Path, required=True)
    child = sub.add_parser('stage-plan-child')
    child.add_argument('--input', type=Path, required=True)
    start = sub.add_parser('begin')
    start.add_argument('--task', type=Path, required=True)
    start.add_argument('--state', type=Path, required=True)
    for name in ['test', 'check']:
        command = sub.add_parser(name)
        command.add_argument('--state', type=Path, required=True)
    finalizing=sub.add_parser('finalize')
    finalizing.add_argument('--state',type=Path,required=True)
    finalizing.add_argument('--input',type=Path)
    finalizing.add_argument('--automatic',action='store_true')
    reading = sub.add_parser('read-symbol')
    reading.add_argument('path')
    reading.add_argument('name')
    reading.add_argument('--offset', type=int, default=0)
    batch = sub.add_parser('read-symbols')
    batch.add_argument('path')
    batch.add_argument('names', nargs='+')
    across = sub.add_parser('read-symbols-across')
    across.add_argument('paths', nargs='+')
    across.add_argument('--names', nargs='+', required=True)
    fixture = sub.add_parser('read-fixture')
    fixture.add_argument('path')
    fixture.add_argument('--offset', type=int, default=0)
    page=sub.add_parser('read-file')
    page.add_argument('path');page.add_argument('--offset',type=int,default=0)
    page.add_argument('--fixture-request',action='store_true')
    variables = sub.add_parser('variables')
    variables.add_argument('path')
    variables.add_argument('--query', default='')
    searching = sub.add_parser('search')
    searching.add_argument('paths', nargs='+')
    searching.add_argument('--pattern', required=True)
    searching.add_argument('--regex', action='store_true')
    return parser.parse_args()


def main() -> int:
    """Dispatch explicit map, context and task validation operations."""
    args = arguments()
    if args.briefs:
        import os
        os.environ['QWEN_WORKFLOW_BRIEFS'] = str(args.briefs.resolve())
    root = args.root.resolve()
    prefixes = args.prefix or ['.']
    import os
    from recovery_source import COMMANDS as recovery_reads
    if os.environ.get('QWEN_WORKFLOW_ROLE') == 'architect' and args.command in recovery_reads:
        from recovery_source import read as read_recovery_source
        result = read_recovery_source(root, args)
        print(json.dumps(result, indent=2))
        return int(result.get('passed') is False)
    import shadow_navigation
    navigation = shadow_navigation.planning_context(args, root, prefixes)
    mapped = navigation[0] if navigation else None
    if args.command == 'finalize':
        from skill_runner import prepare,run
        session=args.state.resolve().parent
        inputs=json.loads(args.input.read_text()) if args.input else {}
        if args.automatic:inputs['automatic']=True
        prepare(session,'task-finalize','code')
        result=run(session,'task-finalize',inputs,'code')['data']
    elif args.command == 'stage-plan-child':
        import os
        if os.environ.get('QWEN_WORKFLOW_ROLE') != 'architect' or not os.environ.get('QWEN_WORKFLOW_PLAN_DRAFT'):
            raise ValueError('Child staging requires a bound architect review')
        from plan_refinement_store import stage
        result = stage(root, prefixes, os.environ['QWEN_WORKFLOW_PLAN_DRAFT'], json.loads(args.input.read_text()))
    elif args.command == 'save-plan':
        import os
        proposal = json.loads(args.input.read_text())
        if os.environ.get('QWEN_WORKFLOW_PLAN_DRAFT'):
            if os.environ.get('QWEN_WORKFLOW_ROLE') != 'architect':
                raise ValueError('Unaccepted draft repair is architect-only')
            from plan_draft import restore
            proposal = restore(root, prefixes, os.environ['QWEN_WORKFLOW_PLAN_DRAFT'], proposal)
        if os.environ.get('QWEN_WORKFLOW_REQUIRE_REFINEMENT')=='1':
            proposal['planning_review']={'required':True,'status':'draft'}
        if os.environ.get('QWEN_WORKFLOW_REPLAN_EVIDENCE'):
            if os.environ.get('QWEN_WORKFLOW_ROLE') != 'architect':
                raise ValueError('Failure recovery is architect-only')
            from planning_service import attach_lineage
            packet=json.loads(Path(os.environ['QWEN_WORKFLOW_REPLAN_EVIDENCE']).read_text())
            if packet['current_snapshot']!=scan(root,prefixes)['snapshot'] or packet['project']!=str(root):
                raise ValueError('Failure evidence became stale')
            if 'tasks' not in proposal:
                from replan_patch import restore as restore_recovery
                proposal=restore_recovery(root,prefixes,packet,proposal)
            analysis=proposal.get('failure_analysis')
            if not isinstance(analysis,str) or len(analysis.strip())<40:raise ValueError('Explain failure evidence, cause, corrective approach and validation in failure_analysis')
            if not {t['id'] for t in packet['remaining']}<={t['id'] for t in proposal['tasks']}:
                raise ValueError('Keep original remaining todo IDs in the repair plan')
            attach_lineage(proposal,packet)
        result = plans.save(root, prefixes, proposal, args.output.resolve())
    elif args.command == 'refresh':
        if args.state:
            from architecture_maintenance import maintain
            session = args.state.resolve().parent
            binding = session / 'launch.json'
            if binding.exists():
                from skill_runner import prepare, run
                launch = json.loads(binding.read_text())
                if Path(launch.get('state','')).resolve() != args.state.resolve() or Path(launch['project']).resolve() != root or Path(launch['shadow']).resolve() != args.output.resolve():
                    raise ValueError('Maintenance launch differs from the frozen task')
                prepare(session, 'architecture-maintenance', 'code')
                result = run(session, 'architecture-maintenance', {}, 'code')['data']
            else:
                result = maintain(root, prefixes, args.output, args.state)
        else:
            result = shadow.refresh(root, prefixes, args.output.resolve())
    elif args.command == 'map':
        result = write_map(scan(root, prefixes), args.output.resolve())
    elif args.command == 'architecture':
        from architecture_map import navigation as render
        limit = max(1, min(args.limit, 10 if navigation and navigation[1]['architecture_only_navigation'] else 20))
        text = render(mapped or scan(root, prefixes), args.paths, max(0, args.offset), limit, max(0, args.section_offset))
        if navigation:
            shadow_navigation.record_architecture(navigation, args.paths, max(0, args.offset), limit)
            print(shadow_navigation.instructions(navigation[1]))
        print(text, end='')
        return 0
    elif args.command in ('architecture-status', 'architecture-rebuild'):
        import architecture_consistency
        handler = architecture_consistency.check if args.command == 'architecture-status' else architecture_consistency.rebuild
        result = handler(root, prefixes, args.shadow, args.state)
    elif args.command == 'architecture-search':
        import architecture_sections
        result = architecture_sections.search(architecture_sections.build(mapped or scan(root, prefixes)), args.query, args.offset)
        if navigation:
            exposed = [row['path'] for row in result['matches'] if row['kind'] == 'file']
            exposed += [p for row in result['matches'] if row['kind'] == 'section' for p in row['files']]
            shadow_navigation.record_section(navigation, exposed)
    elif args.command == 'architecture-section':
        import architecture_sections
        result = architecture_sections.page(mapped or scan(root, prefixes), args.identifier, args.sha256, args.offset)
        if navigation:
            shadow_navigation.record_section(navigation, result['files'])
    elif args.command == 'catalog':
        data = mapped or scan(root, prefixes)
        total = len(data['files'])
        data['files'] = data['files'][args.offset:args.offset + min(args.limit, 80)]
        print(f'FILES {total}; page offset={args.offset}; next={args.offset + len(data["files"])}')
        print(render_catalog(data), end='')
        return 0
    elif args.command == 'locate':
        records = (mapped or scan(root, prefixes))['files']
        if args.paths:
            records = [f for f in records if f['path'] in set(args.paths)]
        matches = [{'path': f['path'], **s} for f in records
                   for s in f['symbols'] if args.query.casefold() in s['name'].casefold()
                   or args.query.casefold() in f['path'].casefold()]
        result = {'matches': matches[:20], 'total': len(matches), 'truncated': len(matches) > 20}
    elif args.command == 'context':
        text = select_context(mapped or scan(root, prefixes), args.paths, args.max_bytes, args.symbol)
        if navigation:
            shadow_navigation.check_selected(navigation[1], text)
        print(text, end='')
        return 0
    elif args.command == 'begin':
        tasks.begin(root, prefixes, json.loads(args.task.read_text()), args.state.resolve())
        result = {'started': str(args.state), 'scope_frozen': True}
    elif args.command == 'read-symbol':
        result = retrieval.read_symbol(root, args.path, args.name, args.offset)
    elif args.command == 'read-fixture':
        result = retrieval.read_fixture(root, args.path, args.offset)
    elif args.command == 'read-file':
        result = retrieval.read_page(root, args.path, args.offset, args.fixture_request)
    elif args.command == 'read-symbols':
        result = retrieval.read_symbols(root, args.path, args.names)
    elif args.command == 'read-symbols-across':
        from retrieval_batch import read_across
        result = read_across(root, args.paths, args.names)
    elif args.command == 'variables':
        result = retrieval.variables(root, args.path, args.query)
    elif args.command == 'search':
        result = retrieval.search(root, args.paths, args.pattern, args.regex)
    elif args.command == 'test':
        result = tasks.run_tests(args.state.resolve())
    else:
        result = tasks.check(args.state.resolve())
    print(json.dumps(result, indent=2))
    if args.command == 'test':
        return int(any(row['exit_code'] for row in result['results']))
    return int(result.get('passed') is False or bool(result.get('parse_errors')))


if __name__ == '__main__':
    raise SystemExit(main())
