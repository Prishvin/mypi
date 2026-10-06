"""Cancel an owned workflow tree, preserving the independently guarded model service."""
import os
import signal
import subprocess
import time
from config import ROOT
import quality_service


def processes():
    """List live processes; exited zombies cannot run tools or handle signals."""
    raw=subprocess.check_output(['ps','-axo','pid=,ppid=,pgid=,stat='],text=True)
    return {int(p):(int(parent),int(group)) for p,parent,group,state in
            (line.split() for line in raw.splitlines() if line.strip()) if not state.startswith('Z')}


def descendants(root,table):
    found={root}
    while True:
        more={pid for pid,(parent,_) in table.items() if parent in found}
        if more<=found:return found
        found.update(more)


def terminate(process, grace=8):
    """Stop nested detached Pi/phase children as well as the web-owned parent."""
    if process is None:return
    table=processes();owned=descendants(process.pid,table)
    state=quality_service.read_state();guard=state.get('guard_pid')
    protected=descendants(guard,table) if isinstance(guard,int) else set()
    owned-=protected
    groups={table[pid][1] for pid in owned if pid in table}-{os.getpgrp()}
    if not groups:return
    for group in groups:
        try:os.killpg(group,signal.SIGINT)
        except ProcessLookupError:pass
    deadline=time.monotonic()+grace
    while time.monotonic()<deadline:
        current=processes()
        if not any(pid in current and current[pid][1] in groups for pid in owned):break
        time.sleep(.1)
    current=processes()
    for pid in owned:
        if pid in current and current[pid][1] in groups:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:pass
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        current=processes()
        if not any(pid in current and current[pid][1] in groups for pid in owned):break
        time.sleep(.05)
