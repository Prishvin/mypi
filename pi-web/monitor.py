"""Sample actual model process RSS during web turns without querying model output."""
import json
import subprocess
import threading
import time
from pathlib import Path
import quality_service
import server_config


class Monitor:
    def __init__(self,job,field='metrics'):self.job=job;self.field=field;self.done=threading.Event();self.peak=0;self.started=time.monotonic()
    def __enter__(self):
        threading.Thread(target=self.sample,daemon=True).start();return self
    def sample(self):
        while not self.done.is_set():
            try:
                value=server_config.get('/health',timeout=2).get('server_rss_bytes')
                if isinstance(value,int):self.peak=max(self.peak,value)
            except (OSError,ValueError,subprocess.SubprocessError):pass
            self.done.wait(3)
    def __exit__(self,*_):
        self.done.set()
        row=self.job.store.get(self.job.ident);metrics=row.get(self.field,{})
        metrics['server_rss_peak_sampled_bytes']=self.peak
        if self.field!='metrics':metrics['wall_seconds']=round(time.monotonic()-self.started,2)
        self.job.store.update(self.job.ident,**{self.field:metrics})
