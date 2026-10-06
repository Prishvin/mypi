"""Exercise real HTTP endpoint admission, streaming and preserved request controls."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import launch
import server_config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server_proxy import handler


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'server.json'
        self.environment = patch.dict(os.environ, {'MYPI_SERVER_CONFIG': str(self.config)}, clear=False)
        self.environment.start(); self.addCleanup(self.environment.stop)
        os.environ.pop('MYPI_SERVER_URL', None); os.environ.pop('MYPI_MODEL', None); os.environ.pop('MYPI_SERVER_TOKEN', None)
        self.health = {'ok': True, 'context_window': 98304, 'preserve_thinking': 'auto', 'startup': {'pid': os.getpid()}}
        self.caps = {'version': 1, 'thinking_cap': 'request-local', 'field': 'pi_thinking_cap'}
        self.received = []
        owner = self
        class Native(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                values = {'/health': owner.health, '/v1/models': {'data': [{'id': 'mtplx-quality'}]},
                          '/pi-workflow/capabilities': owner.caps, '/metrics': {'recent': []}}
                raw = json.dumps(values[self.path]).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_POST(self):
                owner.received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'); self.wfile.flush()
        self.native = self.start_server(Native)
        self.url = f'http://127.0.0.1:{self.native.server_port}'

    def start_server(self, implementation):
        server = ThreadingHTTPServer(('127.0.0.1', 0), implementation)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def close(): server.shutdown(); server.server_close(); thread.join()
        self.addCleanup(close)
        return server

    def test_default_and_normalized_addresses(self):
        self.assertEqual(server_config.load()['url'], 'http://localhost:8000')
        for value, expected in [('192.168.1.34:8000', 'http://192.168.1.34:8000'),
                                ('localhost', 'http://localhost:8000'),
                                ('https://example.com/v1/', 'https://example.com'),
                                ('[::1]:8000', 'http://[::1]:8000')]:
            self.assertEqual(server_config.normalize(value), expected)
        for value in ('ftp://example.com', 'http://user:password@example.com', 'localhost:0', 'localhost:99999', 'http://host/project', 'http://host?token=secret'):
            with self.assertRaises(ValueError): server_config.normalize(value)

    def test_saved_endpoint_is_verified_and_failed_admission_keeps_previous(self):
        good = server_config.save(server_config.validate(self.url))
        self.assertEqual(server_config.load()['url'], self.url)
        self.assertEqual(good['context_window'], 98304)
        original = self.config.read_bytes()
        self.caps['thinking_cap'] = 'global'
        with self.assertRaisesRegex(ValueError, 'adapter'):
            server_config.save(server_config.validate(self.url))
        self.assertEqual(self.config.read_bytes(), original)
        self.caps['thinking_cap'] = 'request-local'; self.health['context_window'] = 65536
        with self.assertRaisesRegex(ValueError, '98304'):
            server_config.validate(self.url, minimum_context=98304)
        self.assertEqual(self.config.read_bytes(), original)

    def test_configured_provider_uses_remote_endpoint_and_model(self):
        with patch.dict(os.environ, {'MYPI_SERVER_URL': self.url, 'MYPI_MODEL': 'qwen-remote'}):
            destination = Path(self.temp.name) / 'pi-config'
            launch.configure(destination, 'quality', 98304)
            provider = json.loads((destination / 'models.json').read_text())['providers']['local-qwen-workflow']
            self.assertEqual(provider['baseUrl'], self.url + '/v1')
            self.assertEqual(provider['models'][0]['id'], 'qwen-remote')
            self.assertEqual(provider['models'][0]['contextWindow'], 98304)

    def test_proxy_streams_unchanged_controls_and_publishes_host_rss(self):
        proxy = self.start_server(handler(self.url, None))
        target = f'http://127.0.0.1:{proxy.server_port}'
        with urlopen(target + '/health') as response: health = json.load(response)
        self.assertGreater(health['server_rss_bytes'], 0)
        self.assertFalse(health['mypi_gateway']['model_process_owned'])
        payload = {'model': 'mtplx-quality', 'stream': True, 'max_tokens': 4096,
                   'metadata': {'client': 'pi', 'pi_thinking_cap': 512}, 'messages': [{'role': 'user', 'content': 'test'}]}
        with urlopen(Request(target + '/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})) as response:
            self.assertIn(b'data: [DONE]', response.read())
        self.assertEqual(self.received, [payload])
        with self.assertRaises(HTTPError) as error: urlopen(target + '/project/files')
        self.assertEqual(error.exception.code, 404)

    def test_proxy_token_is_required_when_configured(self):
        proxy = self.start_server(handler(self.url, 'test-only-token'))
        target = f'http://127.0.0.1:{proxy.server_port}/health'
        with self.assertRaises(HTTPError) as error: urlopen(target)
        self.assertEqual(error.exception.code, 401)
        with urlopen(Request(target, headers={'Authorization': 'Bearer test-only-token'})) as response:
            self.assertTrue(json.load(response)['ok'])


if __name__ == '__main__': unittest.main()
