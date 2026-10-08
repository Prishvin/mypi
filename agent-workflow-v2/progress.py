"""Own noninteractive Pi descendants and publish durable thirty-second progress."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(path)


def stop(process):
    """Cancel the owned group, including children after its leader has exited."""
    try: os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError: return
    try: process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    try: os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError: pass


def run(command, cwd, env, prepared):
    session = Path(prepared['session'])
    started = time.monotonic()
    interval = prepared.get('progress_seconds', 30)
    state = {'attempt_id': uuid.uuid4().hex, 'started_epoch': time.time(), 'status': 'starting'}
    previous = {}
    def interrupted(*_): raise KeyboardInterrupt
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, interrupted)
    process = None
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env,
                                   stdin=None if prepared.get('interactive') else subprocess.DEVNULL,
                                   start_new_session=True)
        state.update(pid=process.pid, process_group=process.pid, owner_pid=os.getpid(), status='running')
        save(session/'process.json', state)
        while True:
            if prepared['role']=='architect' and (session/'recovery-report.json').exists():
                from recovery_report import verified as verified_report
                report=verified_report(session)
                if (report and report['finished_epoch']>=state['started_epoch'] and
                        (prepared.get('timeout_seconds') is None or
                         report['finished_epoch']<=state['started_epoch']+prepared['timeout_seconds'])):
                    stop(process)
                    state.update(status='recovery_stopped',reason=report['decision']['action'],
                                 process_exit_code=process.returncode,exit_code=20,ended_epoch=time.time())
                    process.returncode=20
                    return process
            if prepared['role']=='architect' and prepared.get('plan') and not prepared.get('interactive'):
                from planner_stop import verified
                try: published=json.loads((session/'planning-stop.json').read_text()).get('finished_epoch')
                except (OSError,ValueError):published=None
                in_time=(isinstance(published,(int,float)) and published>=state['started_epoch'] and
                         (prepared.get('timeout_seconds') is None or published<=state['started_epoch']+prepared['timeout_seconds']))
                if in_time and verified(prepared['project'],prepared['plan'],session,current_source=True):
                    stop(process)
                    state.update(status='accepted',reason='validated_plan_saved',
                                 process_exit_code=process.returncode,exit_code=0,ended_epoch=time.time())
                    process.returncode=0
                    return process
            remaining = prepared.get('timeout_seconds')
            if remaining is not None:
                remaining -= time.monotonic() - started
                if remaining <= 0:
                    stop(process)
                    process.returncode = 124
                    state.update(status='timed_out', exit_code=124, ended_epoch=time.time())
                    return process
            try:
                poll=min(interval,1) if prepared['role']=='architect' else interval
                process.wait(timeout=min(poll, remaining) if remaining is not None else poll)
                state.update(status='finished',exit_code=process.returncode,ended_epoch=time.time())
                return process
            except subprocess.TimeoutExpired:
                if prepared['role']=='architect' and time.monotonic()-started < state.get('next_report',interval):
                    continue
                state['next_report']=time.monotonic()-started+interval
                try: activity = json.loads((session/'last-activity.json').read_text())
                except (OSError, ValueError): activity = {}
                report = {'elapsed_seconds': round(time.monotonic()-started), 'role': prepared['role'],
                          'todo': prepared.get('todo'), 'activity': activity.get('activity','Pi is starting'),
                          'session': str(session), 'attempt_id': state['attempt_id']}
                state['heartbeat_epoch'] = time.time()
                save(session/'process.json',state)
                with (session/'progress.jsonl').open('a') as log: log.write(json.dumps(report)+'\n')
                print(f"[{report['elapsed_seconds']}s] {report['role']}: {report['activity']}",file=sys.stderr,flush=True)
    except BaseException as error:
        state.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',
                     ended_epoch=time.time(),error=type(error).__name__)
        raise
    finally:
        if process is not None: stop(process)
        save(session/'process.json',state)
        for sig, handler in previous.items(): signal.signal(sig,handler)
