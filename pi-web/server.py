"""Local/LAN web UI: persisted conversations, bounded actions, genuine Pi RPC."""
import argparse
import json
import mimetypes
import secrets
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from config import BASE, settings
from store import Store
from processes import Jobs
import workflows
from stats import aggregate


class App:
    def __init__(self,data):
        self.store=Store(data);self.jobs=Jobs(self.store);self.token=secrets.token_urlsafe(32)
        self.monitors={}
        self.run_controls={}
    def monitor(self,ident):
        return self.run_monitor(ident).snapshot()
    def run_monitor(self,ident):
        from run_monitor import RunMonitor
        row=self.store.get(ident)
        selected=row.get('planning_dir') or row.get('run_dir')
        if not selected:raise ValueError('This conversation has no planning or execution run yet')
        folder=Path(selected).resolve()
        item=self.monitors.get(ident)
        if item is None or item.folder!=folder:self.monitors[ident]=item=RunMonitor(folder)
        return item
    def controls(self,ident):
        from run_controls import Controls
        monitor=self.run_monitor(ident)
        item=self.run_controls.get(ident)
        if item is None or item.monitor is not monitor:self.run_controls[ident]=item=Controls(monitor)
        return item
    def view(self,ident):
        row=self.store.get(ident);project=Path(row['project'])
        if row.get('run_dir'):
            target=Path(row['run_dir'])/'execution-target.json'
            if target.exists():
                selected=json.loads(target.read_text());row['plan']=selected['plan'];row['run_dir']=selected['run_dir']
        for name in ('knowledge','architecture'):
            path=project/(name+'.md')
            row[name]=path.read_text()[:24000] if path.is_file() and not path.is_symlink() else ''
        row['plan_data']=json.loads(Path(row['plan']).read_text()) if row.get('plan') else None
        if row.get('run_dir'):
            for name in ('state.json','run-result.json','final-review/result.json','final-review/review.json'):
                file=Path(row['run_dir'])/name
                if file.exists():row[name]=json.loads(file.read_text())
            state=row.get('state.json',{})
            if state.get('attempts'):row['execution_metrics']=aggregate(state['attempts'])
            observation=row.get('execution_observation',{})
            if row.get('execution_metrics') and observation:
                row['execution_metrics']['server_rss_peak_sampled_bytes']=max(row['execution_metrics'].get('server_rss_peak_sampled_bytes',0),observation.get('server_rss_peak_sampled_bytes',0))
            review=row.get('final-review/result.json',{})
            if review.get('metrics'):row['review_metrics']={**review['metrics'],'wall_seconds':review.get('wall_seconds',0)}
        return row
    def action(self,ident,action,data):
        row=self.store.get(ident)
        if action=='stop':self.jobs.stop(ident);return {'ok':True}
        if action=='answer':self.jobs.answer(ident,data['id'],data.get('value'));return {'ok':True}
        if row['busy']:raise ValueError('Wait for this turn or stop it before changing the conversation')
        if action=='settings':return self.store.update(ident,settings=settings(data,row['settings']))
        if action=='followup':
            from followup import adopt
            return adopt(self.store,ident)
        if action=='rename':
            title=data.get('title','').strip()
            if not title or len(title)>120:raise ValueError('Title must contain 1–120 characters')
            return self.store.update(ident,title=title)
        if action=='message':
            text=data.get('text','').strip()
            if not text or len(text.encode())>48000:raise ValueError('Message must contain 1–48000 bytes')
            first=text.split()[0]
            if text.startswith('/') and first not in ('/server','/remember','/planner','/reviewer','/thinkingcap','/develop','/resume-planning','/resume-request','/rebuild') and '/' not in first[1:] and not Path(first).is_dir():
                raise ValueError('Supported commands: /server, /remember, /planner, /reviewer, /thinkingcap, /develop, /resume-planning, /rebuild')
            self.store.message(ident,'user',text,mode=row['settings']['mode'])
            if row['title']=='New conversation':self.store.update(ident,title=text[:70])
            self.jobs.submit(ident,workflows.turn,text,bool(data.get('develop')))
        elif action in ('execute','replan'):
            if row['settings']['mode']!='pi':raise ValueError('Choose Pi to run a development workflow')
            self.jobs.submit(ident,getattr(workflows,action))
        else:raise ValueError('Unknown action')
        return {'ok':True}


def handler(app,allowed_addresses=()):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,data,kind='application/json'):
            raw=json.dumps(data,ensure_ascii=False).encode() if kind=='application/json' else data
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(raw)
        def security(self,mutate=False):
            port=self.server.server_address[1];hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
            hosts.update(f'{address}:{port}' for address in allowed_addresses)
            if self.headers.get('Host') not in hosts:raise PermissionError('Invalid local host')
            origin=self.headers.get('Origin')
            if origin and origin not in {'http://'+host for host in hosts}:raise PermissionError('Cross-origin access rejected')
            if mutate and self.headers.get('X-Local-Token')!=app.token:raise PermissionError('Missing local browser token')
        def dispatch(self,method):
            try:
                self.security(method!='GET');parts=urlsplit(self.path).path.strip('/').split('/')
                if method=='GET' and parts[0]!='api':
                    name='index.html' if parts in ([''],['workspace']) else 'monitor.html' if parts==['monitor'] else '/'.join(parts)
                    file=(BASE/'static'/name).resolve()
                    if not file.is_relative_to(BASE/'static') or not file.is_file():raise KeyError('Page not found')
                    return self.reply(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
                if parts==['api','bootstrap'] and method=='GET':
                    return self.reply(200,{'application':'mypi','token':app.token,'capacity':98304,'model':'MTPLX Quality','conversations':app.store.listing()})
                data={}
                if method=='POST':
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=65536:raise ValueError('Invalid request size')
                    if self.headers.get_content_type()!='application/json':raise ValueError('JSON required')
                    data=json.loads(self.rfile.read(size))
                    if not isinstance(data,dict):raise ValueError('JSON object required')
                if parts==['api','conversations']:
                    return self.reply(200,app.store.create(data.get('settings')) if method=='POST' else app.store.listing())
                if parts==['api','projects'] and method=='POST':
                    prompt=data.get('prompt','')
                    if not isinstance(prompt,str) or not prompt.strip() or len(prompt.encode())>24000:raise ValueError('Project prompt must contain 1–24000 bytes')
                    row=app.store.create({'mode':'pi'})
                    app.action(row['id'],'message',{'text':'Develop a new project from these requirements:\n'+prompt.strip(),'develop':True})
                    return self.reply(202,{'id':row['id'],'project':row['project']})
                if len(parts)>=3 and parts[:2]==['api','conversations']:
                    ident=parts[2]
                    if method=='GET' and len(parts)==4 and parts[3]=='monitor':return self.reply(200,app.monitor(ident))
                    if method=='GET' and len(parts)==5 and parts[3:]==['monitor','file']:
                        from monitor_files import preview
                        return self.reply(200,preview(app.run_monitor(ident),urlsplit(self.path).query))
                    if len(parts)==5 and parts[3:]==['monitor','control']:
                        return self.reply(202 if method=='POST' else 200,
                            app.controls(ident).restart(data) if method=='POST' else app.controls(ident).view())
                    if method=='GET' and len(parts)==3:return self.reply(200,app.view(ident))
                    if method=='DELETE' and len(parts)==3:return self.reply(200,app.store.delete(ident))
                    if method=='POST' and len(parts)==4:return self.reply(200,app.action(ident,parts[3],data))
                raise KeyError('Endpoint not found')
            except PermissionError as error:self.reply(403,{'error':str(error)})
            except FileNotFoundError as error:self.reply(404,{'error':str(error)})
            except KeyError as error:self.reply(404,{'error':str(error)})
            except (ValueError,TypeError) as error:self.reply(400,{'error':str(error)})
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception as error:
                __import__('traceback').print_exc();self.reply(500,{'error':str(error)[:1000]})
        def do_GET(self):self.dispatch('GET')
        def do_POST(self):self.dispatch('POST')
        def do_DELETE(self):self.dispatch('DELETE')
    return Handler


def main():
    import ipaddress
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8099);parser.add_argument('--data',type=Path,default=BASE/'data')
    parser.add_argument('--listen',type=ipaddress.IPv4Address,default=ipaddress.IPv4Address('127.0.0.1'))
    parser.add_argument('--allow-address',type=ipaddress.IPv4Address,action='append',default=[])
    args=parser.parse_args();app=App(args.data);server=ThreadingHTTPServer((str(args.listen),args.port),handler(app,[str(a) for a in args.allow_address]))
    def stop(*_):
        app.jobs.close();threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    print(f'Pi + Qwen: listen={args.listen}:{args.port}; allowed LAN addresses={args.allow_address}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()


if __name__=='__main__':main()
