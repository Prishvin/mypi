"""Read only explicit Pi reasoning events for the active attempt, with bounded memory."""
import json
from pathlib import Path
import threading


class ThinkingFeed:
    """Incrementally follow one log; never expose prompts, tool arguments or answers."""
    def __init__(self, read_limit=524288, text_limit=16000):
        self.read_limit=read_limit;self.text_limit=text_limit;self.lock=threading.Lock()
        self.reset(None)

    def reset(self, identity):
        """Discard another attempt's text and any partially written record."""
        self.identity=identity;self.offset=0;self.pending=b'';self.discard=False
        self.text='';self.streaming=False;self.previous=False;self.truncated=False

    def content(self, text, append=False):
        """Retain the latest reasoning block, keeping at most the visible tail."""
        if not isinstance(text,str):return
        full=self.text+text if append else text
        self.truncated=(self.truncated if append else False) or len(full)>self.text_limit
        self.text=full[-self.text_limit:];self.previous=False

    def event(self, event):
        """Consume explicit thinking fields; never parse reasoning out of other text."""
        if not isinstance(event,dict):return
        kind=event.get('type');message=event.get('message')
        if kind=='message_start' and isinstance(message,dict) and message.get('role')=='assistant':
            self.streaming=False;self.previous=bool(self.text)
        update=event.get('assistantMessageEvent')
        if kind=='message_update' and isinstance(update,dict):
            phase=update.get('type')
            if phase=='thinking_start':
                self.content('');self.streaming=True
            elif phase=='thinking_delta':
                if self.previous:self.content('')
                self.content(update.get('delta'),append=True);self.streaming=True
            elif phase=='thinking_end':
                self.content(update.get('content'));self.streaming=False
            elif phase in ('text_start','text_delta','toolcall_start','toolcall_delta'):
                self.streaming=False
        if kind=='message_end' and isinstance(message,dict) and message.get('role')=='assistant':
            blocks=message.get('content',[])
            if isinstance(blocks,list):
                for block in blocks:
                    if isinstance(block,dict) and block.get('type')=='thinking':self.content(block.get('thinking'))
            self.streaming=False

    def snapshot(self, path, running=False):
        """Read new bytes only; tolerate rotation, partial JSON/UTF-8 and missed tails."""
        with self.lock:
            try:
                with Path(path).open('rb') as stream:
                    import os
                    info=os.fstat(stream.fileno());identity=(str(path),info.st_dev,info.st_ino)
                    if identity!=self.identity or info.st_size<self.offset:self.reset(identity)
                    if info.st_size-self.offset>self.read_limit:
                        self.offset=info.st_size-self.read_limit;self.pending=b'';self.discard=True
                        self.text='';self.previous=False;self.streaming=False;self.truncated=True
                    stream.seek(self.offset);raw=stream.read(self.read_limit);self.offset+=len(raw)
                lines=(self.pending+raw).split(b'\n');self.pending=lines.pop()
                for line in lines:
                    if self.discard:self.discard=False;continue
                    try:self.event(json.loads(line))
                    except (ValueError,UnicodeError):pass
                if len(self.pending)>self.read_limit:
                    self.pending=b'';self.discard=True;self.truncated=True
            except OSError:
                self.reset(None)
            return {'text':self.text,'streaming':running and self.streaming,
                    'previous':self.previous,'truncated':self.truncated,'source':'Pi reasoning output'}
