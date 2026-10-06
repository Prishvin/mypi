"""Client compatibility layer: verify a configured server, never own its processes."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / 'agent-workflow-v2'
sys.path.insert(0, str(WORKFLOW))
import server_config


def read_state():
    """No remote PIDs or local model logs may be used for client cancellation."""
    return {'endpoint': server_config.load()['url'], 'remote': True}


def start(timeout=180):
    """An ordinary client request verifies availability without launching weights."""
    connection = server_config.load()
    return server_config.validate(connection['url'], connection['model'])


def stop(timeout=20):
    raise ValueError('mypi is a client: it cannot stop the shared Qwen model. Stop its owner on the server Mac.')


def status():
    """Report actual remote health and controls without loading or changing models."""
    connection = server_config.load()
    try:
        health = server_config.get('/health', connection)
        return {'status': 'ready' if health.get('ok') else 'unavailable', 'owned': False,
                'endpoint': connection['url'] + '/v1', 'context': health.get('context_window'),
                'mode': health.get('generation_mode'), 'depth': health.get('depth'),
                'kv': health.get('paged_kv_quantization'),
                'thinking_caps': server_config.get('/pi-workflow/capabilities', connection)}
    except (OSError, ValueError) as error:
        return {'status': 'unavailable', 'owned': False, 'endpoint': connection['url'] + '/v1', 'error': str(error)}


# Older callers import ENDPOINT; new requests use server_config.load() so /server is live.
ENDPOINT = server_config.load()['url']
