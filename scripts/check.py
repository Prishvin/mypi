"""Run the same release checks from a fresh macOS/Linux installation."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
commands = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'agent-workflow-v2'],
            [sys.executable, '-m', 'unittest', 'discover', '-s', 'pi-web/tests'],
            [sys.executable, '-m', 'unittest', 'discover', '-s', 'qwen-host'],
            ['npm', 'test']]
for command in commands:
    result = subprocess.run(command, cwd=root)
    if result.returncode:
        raise SystemExit(result.returncode)
