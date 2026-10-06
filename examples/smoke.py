"""Prove a genuine Pi worker edits/tests one atomic task against configured Qwen."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'agent-workflow-v2'))
from runner_process import invoke

ROOT = Path(__file__).resolve().parent.parent


def prepare(destination: Path) -> tuple[Path, Path]:
    """Create a fresh isolated bug, immutable acceptance fixture and small task."""
    destination.mkdir(parents=True, exist_ok=False)
    project = destination / 'project'; project.mkdir()
    (project / 'arithmetic.py').write_text('"""Pure arithmetic interfaces."""\ndef double(value):\n    """Return twice a numeric or sequence value."""\n    return value\n')
    (project / 'architecture.md').write_text('Pure arithmetic belongs to arithmetic.py; tests specify the public contract.\n')
    subprocess.run(['git', 'init', '-q', str(project)], check=True)
    fixture = destination / 'acceptance.py'
    fixture.write_text('''import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
from arithmetic import double

class Acceptance(unittest.TestCase):
    def test_numbers(self):
        for value in (0, 3, -2, 2.5):
            with self.subTest(value=value): self.assertEqual(double(value), value * 2)
    def test_keyword(self): self.assertEqual(double(value=3), 6)
    def test_sequence(self): self.assertEqual(double("ab"), "abab")
    def test_invalid(self):
        with self.assertRaises(TypeError): double(None)

if __name__ == '__main__': unittest.main()
''')
    cases = [{'id': 'A1', 'given': 'signed numeric input or zero', 'when': 'double(value)', 'then': 'return twice the value'},
             {'id': 'A2', 'given': 'value=3 as a keyword', 'when': 'double(value=3)', 'then': 'return 6, preserving the parameter name'},
             {'id': 'A3', 'given': 'string ab', 'when': 'double("ab")', 'then': 'return abab'},
             {'id': 'A4', 'given': 'None', 'when': 'double(None)', 'then': 'raise TypeError'}]
    task = {'id': 'T1', 'goal': 'Fix double(value) to satisfy the four frozen acceptance cases. Keep the existing signature and module responsibilities.',
            'files': ['arithmetic.py'], 'acceptance': cases,
            'tests': [[sys.executable, str(fixture), str(project)]],
            'steps': ['Inspect double and the selected acceptance fixture.', 'Make the smallest pure-function fix.', 'Run the frozen tests and verify the fresh gate.'],
            'assumptions': [], 'test_strategy': 'Four CPU unit tests cover signed/zero/float input, keyword compatibility, string repetition and invalid input.',
            'estimated_changed_lines': 5, 'depends_on': [],
            'coverage': [{'criterion': case['id'], 'test': 0} for case in cases],
            'execution': {'timeout_seconds': 300, 'test_timeout_seconds': 20, 'on_failure': 'replan'},
            'context': {'interfaces': ['arithmetic.py'], 'symbols': [{'path': 'arithmetic.py', 'name': 'double'}],
                        'reference_files': [], 'window_tokens': 32768, 'max_input_tokens': 16384,
                        'max_output_tokens': 8192, 'thinking': 'on', 'reasoning_effort': 'medium',
                        'reasoning_budget_tokens': 512, 'knowledge_topics': [],
                        'estimate': {'framework': 7168, 'shadow': 256, 'source': 512, 'tests': 512, 'history': 0},
                        'margin_tokens': 2112}}
    path = destination / 'task.json'; path.write_text(json.dumps(task, indent=2))
    return project, path


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('destination', type=Path)
    args = parser.parse_args(); destination = args.destination.resolve()
    project, task = prepare(destination)
    command = [str(ROOT / 'agent-workflow-v2/qwen-agent'), '--profile', 'mtplx-quality',
               '--project', str(project), '--role', 'code', '--task', str(task), '--batch', '--json',
               '--quiet']
    result = invoke(command, destination / 'attempt', 300)
    if result['exit_code']:
        raise SystemExit(result['exit_code'])
    session = Path(result['session'])
    import tasks
    from run_metrics import collect
    gate = tasks.check(session / 'task-state.json')
    shutil.copytree(session, destination / 'session-evidence', ignore=shutil.ignore_patterns('runtime', 'pi-config'))
    summary = {'passed': gate['passed'], 'gate': gate, 'metrics': collect(result, destination / 'attempt'),
               'wall_seconds': result['wall_seconds'],
               'session': str(session), 'project': str(project), 'model_requests': 'see metrics.requests'}
    (destination / 'result.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return int(not gate['passed'])


if __name__ == '__main__': raise SystemExit(main())
