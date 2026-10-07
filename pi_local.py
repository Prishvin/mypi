"""A portable client for Qwen and the private mypi workflow."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from quality_service import ENDPOINT, ROOT, WORKFLOW, start, status, stop

COMMANDS = {'start', 'stop', 'status', 'web', 'chat', 'plan', 'run', 'execute', 'resume', 'replan', 'research', 'skills','review','settings', 'web-raw', 'server', 'serve', 'login', 'setup-qwen', 'qwen','monitor','retry'}


def client_command(args, extra):
    """Keep architecture chat and frozen-todo execution in their existing scopes."""
    profile='chatgpt-quality' if args.action=='chat' and getattr(args,'planner','qwen')=='chatgpt' else 'mtplx-quality'
    command = [str(WORKFLOW / 'qwen-agent'), '--profile', profile,
               '--project', str(args.project.resolve()), '--quiet']
    if args.action == 'chat':
        command += ['--role', 'architect', '--interactive']
    elif args.action == 'plan':
        command += ['--role', 'architect', '--batch', '--prompt', args.request]
    else:
        command += ['--role', 'code', '--batch', '--plan', str(args.plan.resolve()), '--todo', args.todo]
    return command + extra


def initialize(project):
    """Support an existing folder or a new local project without requiring a plan."""
    project = project.resolve()
    if project in {Path.home(), ROOT, WORKFLOW, Path('/')}:
        raise ValueError('Choose a project directory, rather than the home or toolkit directory.')
    sys.path.insert(0, str(WORKFLOW))
    import bootstrap
    return bootstrap.initialize(project)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0]=='retry':
        sys.path.insert(0,str(WORKFLOW))
        from retry_plan import create
        p=argparse.ArgumentParser(prog='mypi retry',description='Prepare an explicit unchanged-contract retry; does not start inference')
        p.add_argument('project',type=Path);p.add_argument('--from-run',type=Path,required=True)
        p.add_argument('--out',type=Path,required=True);p.add_argument('--task-timeout',type=int,default=2700)
        a=p.parse_args(argv[1:]);print(json.dumps(create(a.project,a.from_run,a.out,a.task_timeout),indent=2));return 0
    if argv and argv[0]=='monitor':
        sys.path.insert(0,str(WORKFLOW))
        from monitor_server import main as monitor
        return monitor(argv[1:])
    if argv and argv[0] == 'setup-qwen':
        return subprocess.call([str(ROOT / 'setup-qwen.sh'), *argv[1:]])
    if argv and argv[0] == 'qwen':
        sys.path.insert(0, str(ROOT / 'qwen-host'))
        import qwen_config
        python = qwen_config.root() / '.venv/bin/python'
        return subprocess.call([str(python) if python.is_file() else sys.executable,
                                str(ROOT / 'qwen-host/service.py'), *argv[1:]])
    if argv and argv[0] in {'web', 'web-raw'}:
        parser = argparse.ArgumentParser(prog='mypi web', description='Start mypi conversations UI on the client machine')
        parser.add_argument('--port', type=int, default=8099); parser.add_argument('--listen', default='127.0.0.1')
        parser.add_argument('--allow-address', action='append', default=[]); parser.add_argument('--no-open', action='store_true')
        options = parser.parse_args(argv[1:])
        from pi_web_service import start as start_web
        print('mypi web: '+start_web(not options.no_open, options.port, options.listen, options.allow_address)); return 0
    if argv and argv[0] == 'serve':
        from server_proxy import main as serve
        return serve(argv[1:])
    if argv and argv[0] == 'server':
        import server_config
        arguments = argv[1:]
        parser = argparse.ArgumentParser(prog='mypi server', description='Select the Qwen instance without moving project files')
        parser.add_argument('address', nargs='?'); parser.add_argument('--model')
        chosen = parser.parse_args(arguments)
        result = server_config.save(server_config.validate(chosen.address, chosen.model)) if chosen.address else server_config.load()
        print(json.dumps(result, indent=2)); return 0
    if argv and argv[0] == 'login':
        from launch import PI
        import planner
        return planner.login(WORKFLOW, PI)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith('-'):
        argv.insert(0, 'chat')
    parser = argparse.ArgumentParser(prog='mypi', description='Connect to Qwen and use the private mypi workflow.')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('server', help='Show or verify/save a Qwen endpoint (default localhost:8000)')
    sub.add_parser('serve', help='Expose an existing Qwen API to LAN clients; see mypi serve --help')
    sub.add_parser('login', help='Sign this client in for optional ChatGPT subscription planning')
    sub.add_parser('setup-qwen', help='Mac host only: install pinned MTPLX Quality and verify downloads')
    sub.add_parser('qwen', help='Mac host only: start, inspect or stop this installer\'s guarded model')
    starting = sub.add_parser('start', help='Verify the configured shared Qwen server')
    starting.add_argument('--timeout', type=int, default=180)
    sub.add_parser('stop', help='Explain model ownership; clients cannot unload shared Qwen')
    sub.add_parser('status', help='Show actual server controls')
    sub.add_parser('monitor', help='Read-only live todo/tool/test/model dashboard; see mypi monitor --help')
    sub.add_parser('retry',help='Prepare a preserved-contract operational retry; see mypi retry --help')
    sub.add_parser('web', help='Open the combined Pi / raw Qwen web workspace')
    sub.add_parser('web-raw', help='Open the mypi web UI; select raw Qwen')
    chatting = sub.add_parser('chat', help='Open architecture chat; create granular todos from shadow interfaces')
    chatting.add_argument('project', type=Path)
    chatting.add_argument('--planner',choices=['chatgpt','qwen','local'])
    planning = sub.add_parser('plan', help='Create a granular plan from one request, then exit')
    planning.add_argument('project', type=Path)
    planning.add_argument('request', nargs='?')
    planning.add_argument('--request-file', type=Path)
    planning.add_argument('--planner', choices=['chatgpt', 'qwen','local'])
    planning.add_argument('--out', type=Path, required=True)
    planning.add_argument('--timeout', type=int, default=600)
    planning.add_argument('--draft-plan', type=Path, help='Repair an unaccepted model proposal with sparse patches')
    researching = sub.add_parser('research', help='Clarify and research one request; write a concise knowledge.md')
    researching.add_argument('project', type=Path)
    researching.add_argument('request', nargs='?')
    researching.add_argument('--request-file', type=Path)
    researching.add_argument('--planner', choices=['chatgpt', 'qwen','local'])
    researching.add_argument('--out', type=Path, required=True, help='Evidence prefix outside the project')
    researching.add_argument('--timeout', type=int, default=600)
    for command_parser in (planning, researching):
        command_parser.add_argument('--clarifier', choices=['auto','chatgpt','qwen','off'], default='auto')
        command_parser.add_argument('--researcher', choices=['auto','chatgpt','qwen','off'], default='auto')
        command_parser.add_argument('--answers-file', type=Path, help='JSON array of up to two clarification answers')
        command_parser.add_argument('--non-interactive', action='store_true')
        command_parser.add_argument('--refresh-research', action='store_true')
    skills_parser = sub.add_parser('skills', help='List private executable skills or inspect a contract')
    skills_parser.add_argument('name', nargs='?')
    running = sub.add_parser('run', help='Implement and verify one selected todo, then exit')
    running.add_argument('project', type=Path)
    running.add_argument('plan', type=Path)
    running.add_argument('todo')
    executing = sub.add_parser('execute', help='Run all reviewed todos with deterministic scheduling')
    executing.add_argument('project', type=Path)
    executing.add_argument('plan', type=Path)
    executing.add_argument('--run-dir', type=Path, required=True)
    resuming = sub.add_parser('resume', help='Resume interrupted work from the original checkpoint')
    resuming.add_argument('project', type=Path)
    resuming.add_argument('plan', type=Path)
    resuming.add_argument('--run-dir', type=Path, required=True)
    for runner_parser in (executing,resuming):
        runner_parser.add_argument('--reviewer',choices=['chatgpt','qwen','local'])
    reviewing=sub.add_parser('review',help='Review a completed run and save granular follow-up tests/fixes')
    reviewing.add_argument('project',type=Path)
    reviewing.add_argument('plan',type=Path)
    reviewing.add_argument('--run-dir',type=Path,required=True)
    reviewing.add_argument('--reviewer',choices=['chatgpt','qwen','local'])
    reviewing.add_argument('--out',type=Path,help='New review folder, outside the project')
    preferences=sub.add_parser('settings',help='Show or set private project planner/reviewer selection')
    preferences.add_argument('project',type=Path)
    preferences.add_argument('--planner',choices=['chatgpt','qwen','local'])
    preferences.add_argument('--reviewer',choices=['chatgpt','qwen','local'])
    replanning = sub.add_parser('replan', help='Create a replacement plan from a stopped run')
    replanning.add_argument('project', type=Path)
    replanning.add_argument('evidence', type=Path)
    replanning.add_argument('--planner', choices=['chatgpt', 'qwen','local'])
    replanning.add_argument('--out', type=Path, required=True)
    replanning.add_argument('--timeout', type=int, default=600)
    args, extra = parser.parse_known_args(argv)
    try:
        if args.action=='web':
            if extra:parser.error('Unrecognized arguments: '+' '.join(extra))
            from pi_web_service import start as start_web
            print('Pi + Qwen web UI: '+start_web());return 0
        if args.action=='web-raw':args.action='web'
        if args.action in {'start', 'stop', 'status', 'web'}:
            if extra:
                parser.error('Unrecognized arguments: ' + ' '.join(extra))
            if args.action == 'start':
                if args.timeout < 1:
                    parser.error('--timeout must be positive')
                start(args.timeout)
                import server_config
                print('Qwen verified: '+server_config.load()['url']+'/v1 (client only; no weights started)')
            elif args.action == 'web':
                start()
                url = ENDPOINT + '/'
                import webbrowser
                webbrowser.open(url)
                print('MTPLX browser chat: ' + url)
                print('Monitoring dashboard: ' + ENDPOINT + '/dashboard/')
            elif args.action == 'stop':
                stop(); print('Owned Quality server stopped; model unloaded.')
            else:
                print(json.dumps(status(), indent=2))
            return 0
        if args.action == 'skills':
            if extra:
                parser.error('Unrecognized arguments: ' + ' '.join(extra))
            sys.path.insert(0, str(WORKFLOW))
            from skill_registry import catalog, load
            print(json.dumps(load(args.name) if args.name else catalog(), indent=2))
            return 0
        initialize(args.project)
        from role_selection import load,select,backend
        choices=load(args.project)
        if args.action=='settings':
            if extra:parser.error('Unrecognized arguments: '+' '.join(extra))
            for role in ('planner','reviewer'):
                if getattr(args,role):choices=select(args.project,role,getattr(args,role))
            print(json.dumps(choices,indent=2));return 0
        if hasattr(args,'planner'):
            args.planner=backend(args.planner) if args.planner else choices['planner']
        if args.action in {'execute','resume','review'}:
            if extra:parser.error('Unrecognized arguments: '+' '.join(extra))
            selected=backend(args.reviewer) if args.reviewer else choices['reviewer']
            if args.action!='review':
                from plan_runner import execute
                start()
                code=execute(args.project,args.plan,args.run_dir,resume=args.action=='resume')
                if code:return code
            if selected=='qwen':start()
            from review_service import review
            result=review(args.project,args.plan,args.run_dir,selected,output=getattr(args,'out',None))
            print(json.dumps(result,indent=2))
            return 0 if result['passed'] else 21
        if args.action in {'plan', 'research', 'execute', 'resume', 'replan'}:
            if extra:
                parser.error('Unrecognized arguments: ' + ' '.join(extra))
            from planning_service import create
            backends = [args.planner]
            if args.action in {'plan','research'}:
                backends += [getattr(args,name) for name in ('clarifier','researcher')]
            if 'qwen' in backends:
                start()
            if args.action in {'plan','research'}:
                if bool(args.request) == bool(args.request_file):
                    parser.error('Provide one request string or --request-file')
                request = args.request_file.read_text() if args.request_file else args.request
                answers = json.loads(args.answers_file.read_text()) if args.answers_file else None
                if answers is not None and (not isinstance(answers,list) or len(answers)>2 or
                        any(not isinstance(x,str) or not x.strip() for x in answers)):
                    parser.error('--answers-file must contain a JSON array of at most two nonempty answers')
                options = dict(clarifier=args.clarifier,researcher=args.researcher,answers=answers,
                    interactive=sys.stdin.isatty() and not args.non_interactive,refresh=args.refresh_research)
                if args.action == 'plan':
                    result = create(args.project, request, args.out, args.planner, args.timeout,
                                    draft_plan=args.draft_plan, **options)
                else:
                    if args.out.resolve().is_relative_to(args.project.resolve()):
                        parser.error('--out must be outside the project')
                    from request_pipeline import prepare
                    result = prepare(args.project.resolve(), request, args.out.resolve(),args.planner,args.timeout, **options)
            else:
                result = create(args.project, 'Repair the stopped plan from evidence.', args.out,
                                args.planner, args.timeout, args.evidence.resolve())
            print(json.dumps(result, indent=2))
            return 0 if result['passed'] else 2 if result.get('stage')=='awaiting_clarification' else 1
        if args.action!='chat' or args.planner=='qwen':
            start()
            print('Using MTPLX Quality: 96k server capacity; task input remains bounded.', file=sys.stderr)
        return subprocess.call(client_command(args, extra))
    except (OSError, ValueError, RuntimeError) as error:
        print('mypi: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print('mypi: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
