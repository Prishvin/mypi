"""Stopping a turn must also stop detached nested phase processes."""
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from owned_process import terminate,processes


class Cancellation(unittest.TestCase):
    def test_exited_zombie_is_not_a_live_cancellation_target(self):
        with patch('owned_process.subprocess.check_output',return_value='10 1 10 S\n11 10 11 Zs\n'):
            self.assertEqual(processes(),{10:(1,10)})

    def test_detached_descendant_is_stopped(self):
        script="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True); print(p.pid,flush=True); time.sleep(60)"
        parent=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        child=int(parent.stdout.readline())
        try:
            terminate(parent,grace=.3)
            self.assertIsNotNone(parent.poll())
            self.assertNotIn(child,processes())
        finally:
            parent.stdout.close()
            for pid in [parent.pid,child]:
                try:os.kill(pid,9)
                except ProcessLookupError:pass


if __name__=='__main__':unittest.main()
