"""Owned subprocess cancellation and one local-model queue for the web app."""
import os
import signal
import threading
import time
import traceback


class Cancelled(Exception): pass


from owned_process import terminate


class Job:
    def __init__(self,store,ident):
        self.store=store;self.ident=ident;self.cancelled=threading.Event();self.process=None;self.transport=None
        self.dialog_event=threading.Event();self.answer=None
    def check(self):
        if self.cancelled.is_set():raise Cancelled('Stopped. Saved history and project retained; a started plan can be resumed.')
    def note(self,text):self.store.activity(self.ident,text)
    def dialog(self,request):
        self.dialog_event.clear();self.answer=None
        self.store.message(self.ident,'notice',request.get('title') or request.get('message') or 'Clarification needed',
            kind='clarification',dialogue_id=request['id'],options=request.get('options',[]))
        self.store.update(self.ident,dialog=request,status='Waiting for your clarification')
        while not self.dialog_event.wait(.2):self.check()
        self.store.update(self.ident,dialog=None)
        return self.answer
    def cancel(self):
        self.cancelled.set()
        if self.transport and self.transport.sock:
            try:self.transport.sock.shutdown(__import__('socket').SHUT_RDWR)
            except OSError:pass
        threading.Thread(target=terminate,args=(self.process,),daemon=True).start()


class Jobs:
    def __init__(self,store):
        self.store=store;self.jobs={};self.lock=threading.Lock();self.gpu=threading.Lock()
    def submit(self,ident,function,*args):
        with self.lock:
            if ident in self.jobs:raise ValueError('This conversation already has an active job')
            job=Job(self.store,ident);self.jobs[ident]=job
            self.store.update(ident,busy=True,status='Queued',dialog=None)
        threading.Thread(target=self._run,args=(job,function,args),daemon=True).start()
    def _run(self,job,function,args):
        try:
            while not self.gpu.acquire(timeout=.2):job.check()
            try:
                job.check();function(job,*args)
            finally:
                terminate(job.process)
                job.process=None
                self.gpu.release()
        except Exception as error:
            job.note(str(error)[:1500]);self.store.message(job.ident,'notice',str(error)[:3000])
            if not isinstance(error,Cancelled):traceback.print_exc()
        finally:
            terminate(job.process)
            with self.lock:
                self.store.update(job.ident,busy=False,dialog=None);self.jobs.pop(job.ident,None)
    def stop(self,ident):
        with self.lock:job=self.jobs.get(ident)
        if job:job.cancel()
    def answer(self,ident,request_id,value):
        with self.lock:
            job=self.jobs.get(ident);dialog=self.store.get(ident).get('dialog')
            if not job or not dialog or dialog['id']!=request_id or job.dialog_event.is_set():raise ValueError('This clarification is no longer pending')
            reply='Paused clarification' if value is None else 'Yes' if value is True else 'No' if value is False else str(value)
            self.store.message(ident,'notice' if value is None else 'user',reply,mode='pi',kind='clarification-answer',dialogue_id=request_id)
            self.store.update(ident,dialog=None)
            job.answer=value;job.dialog_event.set()
    def close(self):
        for ident in list(self.jobs):self.stop(ident)
