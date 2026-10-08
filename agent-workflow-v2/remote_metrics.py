"""Fetch bounded native telemetry for this client's request IDs, without local PIDs."""
import json
import urllib.request
import server_config


def snapshot(endpoint=None, headers=None):
    """Read one bounded SSE snapshot and close immediately; never generate text."""
    endpoint = endpoint or server_config.load()['url']
    request = urllib.request.Request(endpoint.removesuffix('/v1') + '/v1/mtplx/metrics/stream',
                                     headers=server_config.headers() if headers is None else headers)
    remaining = 2097152
    with urllib.request.urlopen(request, timeout=2) as response:
        for _ in range(10):
            line = response.readline(remaining + 1)
            remaining -= len(line)
            if remaining < 0:
                raise ValueError('Native metrics snapshot exceeds 2 MiB')
            if line.startswith(b'data:'):
                value = json.loads(line[5:])
                if not isinstance(value, dict):
                    raise ValueError('Native metrics snapshot must be an object')
                return value
            if not line:
                break
    raise ValueError('No native metrics snapshot')


def native_for(identity: str) -> list[dict]:
    """Use native decode speed/allocation; never invent throughput from wall time."""
    try:
        metrics = server_config.get('/metrics', timeout=2)
        recent = metrics.get('recent', [])[-32:]
        if metrics.get('latest'):
            recent = recent + [metrics['latest']]
        selected = {row['request_id']: row for row in recent
                    if identity in str(row.get('request_id', ''))}
        return list(selected.values())
    except (OSError, ValueError, KeyError):
        return []
