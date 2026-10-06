"""Atomic conversation persistence. Project folders outlive chat deletion."""
import copy
import json
import re
import threading
import time
import uuid
from pathlib import Path
from config import DEFAULTS, settings


class Store:
    def __init__(self, folder):
        self.folder=Path(folder); self.folder.mkdir(parents=True,exist_ok=True);self.folder.chmod(0o700)
        self.lock=threading.RLock(); self.rows={}
        for file in self.folder.glob('*/conversation.json'):
            row=json.loads(file.read_text())
            if row.get('busy'):
                row.update(busy=False,status='Interrupted by server restart; resend your message or resume the plan.',dialog=None)
            self.rows[row['id']]=row
            self._save(row)

    def _save(self,row):
        folder=self.folder/row['id']; folder.mkdir(exist_ok=True)
        temp=folder/'conversation.tmp';temp.write_text(json.dumps(row,ensure_ascii=False,indent=2));temp.replace(folder/'conversation.json')

    def get(self,ident):
        with self.lock:
            if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{24}',ident) or ident not in self.rows:
                raise KeyError('Conversation not found')
            return copy.deepcopy(self.rows[ident])

    def update(self,ident,**fields):
        with self.lock:
            row=self.get(ident);row.update(fields,updated=time.time());self._save(row);self.rows[ident]=row
            return copy.deepcopy(row)

    def create(self,values=None):
        ident=uuid.uuid4().hex[:24]; folder=self.folder/ident
        project=folder/'project';project.mkdir(parents=True)
        import bootstrap
        bootstrap.initialize(project,create_shadow=False)
        row={'id':ident,'title':'New conversation','created':time.time(),'updated':time.time(),
             'project':str(project),'workspace_project':str(project),'settings':settings(values or {}),'messages':[],
             'busy':False,'status':'Ready','dialog':None,'plan':None,'run_dir':None,'sessions':{},'activity':[]}
        with self.lock: self.rows[ident]=row;self._save(row)
        return copy.deepcopy(row)

    def listing(self):
        with self.lock:
            return [{k:r[k] for k in ['id','title','updated','busy','status','settings']} for r in sorted(self.rows.values(),key=lambda r:r['updated'],reverse=True)]

    def message(self,ident,role,text='',**extra):
        with self.lock:
            row=self.get(ident);message={'id':uuid.uuid4().hex,'role':role,'text':text,'time':time.time(),**extra}
            self.update(ident,messages=row['messages']+[message]);return message['id']

    def edit_message(self,ident,message_id,**fields):
        with self.lock:
            row=self.get(ident)
            for message in row['messages']:
                if message['id']==message_id: message.update(fields);break
            self.update(ident,messages=row['messages'])

    def activity(self,ident,text):
        with self.lock:
            row=self.get(ident);self.update(ident,status=text,activity=(row['activity']+[{'time':time.time(),'text':text}])[-60:])

    def delete(self,ident):
        """Remove chat history while retaining the user's project and run evidence."""
        with self.lock:
            row=self.get(ident)
            if row['busy']:raise ValueError('Stop the active job before deleting this conversation')
            (self.folder/ident/'conversation.json').unlink();del self.rows[ident]
            # Session records contain chat history; keep only project/run artifacts.
            import shutil
            shutil.rmtree(self.folder/ident/'chat',ignore_errors=True)
            return {'deleted':ident,'retained_project':row['project']}
