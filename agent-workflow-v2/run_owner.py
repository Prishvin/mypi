"""Identify the exact native coordinator so UI restarts cannot signal other jobs."""
import os
import subprocess
import time
from runner_process import save


def identity(pid):
    """Include process start time and command to reject stale or reused PIDs."""
    if type(pid) is not int or pid<=1:return ''
    result=subprocess.run(['ps','-p',str(pid),'-o','lstart=','-o','command='],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode==0 else ''


def register(folder, root, plan):
    """Publish ownership after acquiring the recovery coordinator's exclusive lock."""
    save(folder/'coordinator-process.json',{'pid':os.getpid(),'identity':identity(os.getpid()),
        'project':str(root),'plan':str(plan),'epoch':time.time()})
