"""Exercise closed stdin and cancellation with an actual owned child tree."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

BASE=Path(__file__).resolve().parent


class Ownership(unittest.TestCase):
    def test_deadline_terminates_owned_process(self):
        """A real stalled process reaches the bounded timeout rather than hanging a todo."""
        with tempfile.TemporaryDirectory() as folder:
            script=f'import progress,os; p=progress.run([{sys.executable!r},"-c","import time; time.sleep(100)"],{folder!r},os.environ.copy(),{{"session":{folder!r},"role":"code","progress_seconds":.1,"timeout_seconds":.3}}); assert p.returncode==124'
            subprocess.run([sys.executable,'-c',script],cwd=BASE,check=True,timeout=10,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            state=json.loads((Path(folder)/'process.json').read_text())
            self.assertEqual((state['status'],state['exit_code']),('timed_out',124))

    def test_closed_stdin_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            script='import progress,os; progress.run(["'+sys.executable+'","-c","import sys; assert sys.stdin.read()==str()"],"'+folder+'",os.environ.copy(),{"session":"'+folder+'","role":"code","progress_seconds":.1})'
            subprocess.run([sys.executable,'-c',script],cwd=BASE,check=True,timeout=10)
            state=json.loads((Path(folder)/'process.json').read_text())
            self.assertEqual((state['status'],state['exit_code']),('finished',0))
            self.assertTrue(state['attempt_id'])

    def test_cancel_cleans_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            child=root/'child.py'
            child.write_text('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(100)"])\nopen("grandchild.pid","w").write(str(p.pid))\ntime.sleep(100)\n')
            script=f'import progress,os; progress.run([{sys.executable!r},{str(child)!r}],{folder!r},os.environ.copy(),{{"session":{folder!r},"role":"code","progress_seconds":.1}})'
            process=subprocess.Popen([sys.executable,'-c',script],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                deadline=time.monotonic()+10
                while not (root/'grandchild.pid').exists() and time.monotonic()<deadline: time.sleep(.05)
                grandchild=int((root/'grandchild.pid').read_text())
                process.send_signal(signal.SIGTERM);process.wait(timeout=15)
                state=json.loads((root/'process.json').read_text())
                self.assertEqual(state['status'],'interrupted')
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    active=subprocess.run(['/bin/ps','-p',str(grandchild),'-o','stat='],capture_output=True,text=True).stdout.strip()
                    if not active or active.startswith('Z'): break
                    time.sleep(.05)
                self.assertTrue(not active or active.startswith('Z'),active)
            finally:
                if process.poll() is None: os.killpg(process.pid,signal.SIGKILL);process.wait()


if __name__=='__main__': unittest.main()
