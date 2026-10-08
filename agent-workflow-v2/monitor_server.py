"""Serve the built-in read-only mypi todo dashboard for CLI runs."""
import argparse
import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from run_monitor import RunMonitor

STATIC=Path(__file__).resolve().parent.parent/'pi-web/static'


def handler(monitor,addresses=()):
    """Serve a fixed asset allowlist and the bound snapshot; no arbitrary file routes."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            port=self.server.server_address[1];hosts={f'localhost:{port}',f'127.0.0.1:{port}',*[f'{a}:{port}' for a in addresses]}
            if self.headers.get('Host') not in hosts:return self.reply(403,{'error':'Invalid local host'})
            origin=self.headers.get('Origin')
            if origin and origin not in {'http://'+h for h in hosts}:return self.reply(403,{'error':'Cross-origin access rejected'})
            path=urlsplit(self.path).path
            if path=='/api/status':
                try:return self.reply(200,monitor.snapshot())
                except (OSError,ValueError,KeyError):return self.reply(503,{'error':'Run evidence is being updated; retry shortly'})
            if path=='/api/file':
                from monitor_files import preview
                try:return self.reply(200,preview(monitor,urlsplit(self.path).query))
                except PermissionError as error:return self.reply(403,{'error':str(error)})
                except FileNotFoundError as error:return self.reply(404,{'error':str(error)})
                except (ValueError,OSError,KeyError) as error:return self.reply(400,{'error':str(error)})
            assets={'/':('monitor.html','text/html'),'/monitor.html':('monitor.html','text/html'),
                    '/file.html':('file.html','text/html'),'/file-viewer.mjs':('file-viewer.mjs','text/javascript'),
                    '/monitor.js':('monitor.js','text/javascript'),'/monitor-format.mjs':('monitor-format.mjs','text/javascript'),'/monitor.css':('monitor.css','text/css')}
            if path not in assets:return self.reply(404,{'error':'Not found'})
            name,kind=assets[path];self.reply(200,(STATIC/name).read_bytes(),kind)
        def do_POST(self):self.reply(405,{'error':'This monitor is read-only'})
        def reply(self,code,data,kind='application/json'):
            raw=json.dumps(data,ensure_ascii=False).encode() if kind=='application/json' else data
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(raw)
    return Handler


def main(argv=None):
    """Bind a private monitor without initializing or starting the Qwen server."""
    parser=argparse.ArgumentParser(prog='mypi monitor',description=__doc__)
    parser.add_argument('folder',type=Path,help='A run directory or parent evidence folder (follows restarts)')
    parser.add_argument('--port',type=int,default=8137)
    parser.add_argument('--listen',type=ipaddress.IPv4Address,default=ipaddress.IPv4Address('127.0.0.1'))
    parser.add_argument('--allow-address',type=ipaddress.IPv4Address,action='append',default=[])
    args=parser.parse_args(argv);monitor=RunMonitor(args.folder)
    server=ThreadingHTTPServer((str(args.listen),args.port),handler(monitor,[str(a) for a in args.allow_address]))
    print(f'mypi todo monitor: http://127.0.0.1:{args.port}/ (read-only)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
