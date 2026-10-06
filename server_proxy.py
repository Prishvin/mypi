"""Expose an existing Qwen service to mypi clients without loading another model."""
import argparse
import hmac
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

FLOW = Path(__file__).resolve().parent / 'agent-workflow-v2'
sys.path.insert(0, str(FLOW))
import server_config

GET_PATHS = {'/v1/models', '/health', '/metrics', '/pi-workflow/capabilities'}
POST_PATHS = {'/v1/chat/completions', '/v1/completions'}


def connection(url, timeout=1800):
    """Create one independent upstream transport; both HTTP and HTTPS are supported."""
    parts = urlsplit(url)
    factory = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
    return factory(parts.hostname, parts.port, timeout=timeout)


def rss_bytes(health):
    """Sample a same-host server PID from health; no client interprets it as its PID."""
    pid = health.get('startup', {}).get('pid')
    if type(pid) is not int or pid <= 1:
        return None
    try:
        raw = subprocess.check_output(['ps', '-o', 'rss=', '-p', str(pid)], text=True, timeout=2).strip()
        return int(raw) * 1024 if raw else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def handler(upstream: str, token: str | None):
    """Build a narrow API gateway; project files and local shell are not exposed."""
    class Handler(BaseHTTPRequestHandler):
        response_started = False

        def send_response(self, *args, **kwargs):
            self.response_started = True
            super().send_response(*args, **kwargs)

        def log_message(self, format, *args):
            print(time.strftime('%H:%M:%S'), self.client_address[0], format % args, flush=True)

        def reply(self, status: int, value: dict):
            raw = json.dumps(value).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

        def forward(self):
            if token and not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                return self.reply(401, {'error': 'A server bearer token is required'})
            path = urlsplit(self.path).path
            allowed = GET_PATHS if self.command == 'GET' else POST_PATHS
            if path not in allowed or urlsplit(self.path).query:
                return self.reply(404, {'error': 'Unknown model API endpoint'})
            upstream_connection = connection(upstream)
            try:
                body = None
                if self.command == 'POST':
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 4 * 1024 * 1024:
                        return self.reply(413, {'error': 'Send a JSON request within 4 MiB'})
                    body = self.rfile.read(size)
                    if len(body) != size:
                        return self.reply(400, {'error': 'Incomplete request'})
                headers = {'Content-Type': 'application/json'}
                upstream_token = os.environ.get('MYPI_UPSTREAM_TOKEN')
                if upstream_token:
                    headers['Authorization'] = 'Bearer ' + upstream_token
                upstream_connection.request(self.command, path, body=body, headers=headers)
                response = upstream_connection.getresponse()
                if path == '/health' and response.status == 200:
                    health = json.loads(response.read())
                    health['server_rss_bytes'] = rss_bytes(health)
                    health['mypi_gateway'] = {'version': 1, 'model_process_owned': False, 'upstream': upstream}
                    return self.reply(200, health)
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in {'connection', 'transfer-encoding', 'server', 'date'}:
                        self.send_header(key, value)
                self.send_header('Cache-Control', 'no-store'); self.end_headers()
                while chunk := response.read1(8192):
                    self.wfile.write(chunk); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (OSError, ValueError, http.client.HTTPException) as error:
                # Once headers have been streamed, close instead of writing a second response.
                if self.response_started:
                    self.close_connection = True
                else:
                    self.reply(502, {'error': str(error)})
            finally:
                upstream_connection.close()

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

    return Handler


def background(args, argv):
    """Detach only this gateway; record logs/PID outside the Git checkout."""
    folder = Path.home() / '.local/state/mypi/gateway'
    folder.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), *[arg for arg in argv if arg != '--background']]
    with (folder / 'server.log').open('ab') as output:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    (folder / 'pid').write_text(str(process.pid))
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError('Gateway startup exited; see ' + str(folder / 'server.log'))
        try:
            with socket.create_connection(('127.0.0.1' if args.listen == '0.0.0.0' else args.listen, args.port), timeout=.2):
                print(f'mypi Qwen gateway ready on {args.listen}:{args.port}; logs: {folder / "server.log"}')
                return 0
        except OSError:
            time.sleep(.1)
    raise RuntimeError('Gateway startup not ready; see ' + str(folder / 'server.log'))


def main(argv=None):
    """Serve existing Qwen; optionally invoke an explicit host-owned start command."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='mypi serve', description=__doc__)
    parser.add_argument('--upstream', default='http://127.0.0.1:8000')
    parser.add_argument('--listen', default='0.0.0.0'); parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--start-qwen', action='store_true', help='Start/reuse the host installed by setup-qwen.sh first')
    parser.add_argument('--qwen-launcher', type=Path, help='Explicit existing launcher to call with start; optional, server host only')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be 1..65535')
    if args.start_qwen:
        subprocess.run([str(FLOW.parent / 'mypi'), 'qwen', 'start'], check=True)
    if args.qwen_launcher:
        subprocess.run([str(args.qwen_launcher.expanduser().resolve()), 'start'], check=True)
    upstream = server_config.normalize(args.upstream)
    server_config.validate(upstream)
    target = '127.0.0.1' if args.listen == '0.0.0.0' else args.listen
    try:
        with socket.create_connection((target, args.port), timeout=.2):
            existing = server_config.get('/health', {'url': f'http://{target}:{args.port}'})
            if existing.get('mypi_gateway', {}).get('upstream') == upstream:
                print(f'mypi gateway already ready on {args.listen}:{args.port}'); return 0
            raise RuntimeError('The requested address/port is occupied by another service')
    except ConnectionRefusedError:
        pass
    except TimeoutError:
        pass
    if args.background:
        return background(args, argv)
    server = ThreadingHTTPServer((args.listen, args.port), handler(upstream, os.environ.get('MYPI_SERVER_TOKEN')))
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    print(f'mypi Qwen gateway: {args.listen}:{args.port} -> {upstream}; model remains owned by its original launcher', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
