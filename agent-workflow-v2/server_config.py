"""Validated persistent Qwen connections, independent of model-process ownership."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_URL = 'http://localhost:8000'


def config_path() -> Path:
    """Keep endpoint preferences out of both the code project and Git checkout."""
    return Path(os.environ.get('MYPI_SERVER_CONFIG', str(Path.home() / '.config/mypi/server.json'))).expanduser()


def normalize(value: str) -> str:
    """Accept host:port or an HTTP(S) base, including bracketed IPv6 addresses."""
    value = value.strip()
    if '://' not in value:
        if ':' not in value or value.startswith('[') and value.endswith(']'):
            value += ':8000'
        value = 'http://' + value
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError as error:
        raise ValueError('Invalid server port') from error
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path.rstrip('/') not in ('', '/v1')
            or port is not None and not 1 <= port <= 65535):
        raise ValueError('Use ip:port or an http(s) server URL, optionally ending in /v1; no credentials/query')
    return parts.scheme + '://' + parts.netloc


def load() -> dict:
    """Load only connection data; model weights and credentials are never bundled."""
    path = config_path()
    saved = json.loads(path.read_text()) if path.exists() else {}
    url = normalize(os.environ.get('MYPI_SERVER_URL') or saved.get('url', DEFAULT_URL))
    return {**saved, 'url': url, 'model': os.environ.get('MYPI_MODEL') or saved.get('model', 'mtplx-quality')}


def headers() -> dict:
    """A caller may supply a bearer token through its own environment."""
    token = os.environ.get('MYPI_SERVER_TOKEN')
    return {'Authorization': 'Bearer ' + token} if token else {}


def get(path: str, connection=None, timeout=5) -> dict:
    """Read native health/telemetry on the configured endpoint without generation."""
    connection = connection or load()
    with urlopen(Request(connection['url'] + path, headers=headers()), timeout=timeout) as response:
        return json.load(response)


def validate(value: str, model=None, minimum_context=32768) -> dict:
    """Verify identity, real capacity, history policy and request-local cap support."""
    connection = {'url': normalize(value)}
    models = get('/v1/models', connection).get('data', [])
    available = [row['id'] for row in models if isinstance(row.get('id'), str)]
    selected = model or ('mtplx-quality' if 'mtplx-quality' in available else available[0] if len(available) == 1 else None)
    if not selected or selected not in available:
        raise ValueError('Choose a served model explicitly with mypi server HOST:PORT --model ID')
    health = get('/health', connection)
    window = health.get('execution_window') or health.get('context_window')
    capacity = window.get('tokens') if isinstance(window, dict) else window
    caps = get('/pi-workflow/capabilities', connection)
    if not health.get('ok') or type(capacity) is not int or capacity < minimum_context:
        raise ValueError(f'Qwen health must verify at least a {minimum_context}-token execution window')
    if health.get('preserve_thinking') != 'auto':
        raise ValueError('This workflow requires the server preserve_thinking=auto policy')
    if caps.get('version') != 1 or caps.get('thinking_cap') != 'request-local' or caps.get('field') != 'pi_thinking_cap':
        raise ValueError('Server must provide the Pi request-local thinking-cap adapter')
    connection.update(model=selected, context_window=capacity, thinking_caps=caps)
    return connection


def save(connection: dict) -> dict:
    """Publish a completely validated preference atomically with private permissions."""
    path = config_path(); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.server-')
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(connection, output, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return connection


def main():
    """Share one validation contract between terminal and /server commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address', nargs='?'); parser.add_argument('--model')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--minimum-context', type=int, default=32768)
    args = parser.parse_args()
    if args.address:
        result = save(validate(args.address, args.model, args.minimum_context))
    elif args.check:
        current = load(); result = validate(current['url'], current['model'])
    else:
        result = load()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
