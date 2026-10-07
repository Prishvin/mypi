"""Run fixed skill argv with deadlines and bounded output, without a shell."""
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
import threading


class SkillInterrupted(BaseException):
    """Escape selector EINTR handling so parent termination cleans up its child."""


def stop(process):
    """Terminate only the owned skill process group and reap its child."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def execute(argv, folder, timeout, maximum, runtime):
    """Drain stdout/stderr with a shared hard byte limit and process deadline."""
    env = {key: value for key, value in os.environ.items() if key in
           ['PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR']}
    env.update(PYTHONPATH=str(runtime), PYTHONDONTWRITEBYTECODE='1')
    started = time.monotonic()
    process = subprocess.Popen(argv, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    previous=None
    if threading.current_thread() is threading.main_thread():
        previous=signal.getsignal(signal.SIGTERM)
        def interrupted(_signal,_frame):
            raise SkillInterrupted('Skill parent terminated')
        signal.signal(signal.SIGTERM,interrupted)
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    try:
        with selectors.DefaultSelector() as selector:
            for label in output:
                stream = getattr(process, label)
                selector.register(stream, selectors.EVENT_READ, label)
            while selector.get_map():
                if time.monotonic() - started >= timeout:
                    raise ValueError('Skill deadline reached')
                for key, _ in selector.select(timeout=.1):
                    raw = os.read(key.fileobj.fileno(), 4096)
                    if not raw:
                        selector.unregister(key.fileobj)
                        continue
                    output[key.data].extend(raw)
                    if sum(len(b) for b in output.values()) > maximum:
                        raise ValueError('Skill output exceeds its byte limit')
        code = process.wait(timeout=max(.1, timeout - (time.monotonic() - started)))
    except BaseException:
        stop(process)
        raise
    finally:
        if previous is not None:signal.signal(signal.SIGTERM,previous)
        process.stdout.close(); process.stderr.close()
    return {'exit_code': code, 'seconds': round(time.monotonic() - started, 3),
            **{label: data.decode('utf-8', errors='replace') for label, data in output.items()}}
