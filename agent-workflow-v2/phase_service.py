"""Run one isolated model phase with private tools and bounded input/output."""
import json
from runner_process import BASE, invoke, save, read


def run(project, role, request, folder, backend, timeout=300):
    """Preserve each phase's request, result and metrics outside the project."""
    if role not in ('intake', 'research', 'memory') or backend not in ('chatgpt', 'qwen'):
        raise ValueError('Invalid phase or backend')
    folder.parent.mkdir(parents=True, exist_ok=True)
    prompt = folder.with_suffix('.request.txt')
    output = folder.with_suffix('.draft.json')
    if prompt.exists() and prompt.read_text() != request:
        raise ValueError('Phase request changed; choose a new evidence path')
    if output.exists():
        prior = read(folder/'phase-result.json')
        if prior.get('passed') and prior.get('role') == role and prior.get('backend') == backend:
            from research_stop import exit_code
            from pathlib import Path
            if exit_code(0, Path(prior['session']), output, role) == 0:
                return prior, json.loads(output.read_text())
        raise ValueError('Existing phase draft lacks verified completion; review evidence before retrying')
    prompt.write_text(request)
    command = [str(BASE/'qwen-agent'), '--profile', 'chatgpt-quality' if backend == 'chatgpt' else 'mtplx-quality',
               '--project', str(project), '--role', role, '--batch', '--json', '--quiet',
               '--phase-output', str(output), '--prompt-file', str(prompt),
               '--context', '65536', '--input-tokens', '24576', '--output-tokens', '4096' if role=='memory' else '8192',
               '--thinking', 'on', '--reasoning', 'low' if role=='memory' else ('xhigh' if backend=='chatgpt' else 'medium')]
    if backend=='qwen' and role in ('memory', 'research'):
        command += ['--reasoning-budget', '512' if role=='memory' else '1024']
    attempt = folder
    if folder.exists():
        attempt = folder/('retry-' + str(len(list(folder.glob('retry-*')))+1))
    result = invoke(command, attempt, timeout)
    from run_metrics import collect
    result.update(role=role, backend=backend, output=str(output), metrics=collect(result, attempt))
    result['passed'] = result['exit_code'] == 0 and output.is_file()
    save(folder/'phase-result.json', result)
    return result, json.loads(output.read_text()) if result['passed'] else None
