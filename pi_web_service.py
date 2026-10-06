"""Start the portable client UI without managing any model process."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent

def available(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/bootstrap',timeout=2) as response:
            return json.load(response).get('application')=='mypi'
    except (OSError,ValueError):return False


def start(open_browser=True,port=8099,listen='127.0.0.1',allow_address=None):
    url=f'http://127.0.0.1:{port}'
    if not available(port):
        logs=ROOT/'pi-web/logs';logs.mkdir(parents=True,exist_ok=True)
        addresses=allow_address or []
        network=['--listen',listen,*[value for address in addresses for value in ('--allow-address',address)]]
        (ROOT/'pi-web/static/network.json').write_text(json.dumps({'lan_base_url':f'http://{addresses[0]}:{port}' if addresses else None}))
        with (logs/'server.log').open('ab') as log:
            process=subprocess.Popen([str(ROOT/'agent-workflow-v2/.venv/bin/python'),str(ROOT/'pi-web/server.py'),'--port',str(port),*network],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        (logs/'pid').write_text(str(process.pid))
        for _ in range(50):
            if available(port):break
            if process.poll() is not None:raise RuntimeError('mypi UI startup failed; choose a free port or inspect '+str(logs/'server.log'))
            time.sleep(.1)
        else:raise RuntimeError('mypi UI did not become ready')
    if open_browser:webbrowser.open(url)
    return url
