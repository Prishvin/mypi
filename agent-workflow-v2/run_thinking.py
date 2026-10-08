"""Read only explicit Pi reasoning events for the active attempt, with bounded memory."""
import json
from pathlib import Path
import threading


class ThinkingFeed:
    """Incrementally follow one log; never expose prompts, tool arguments or answers."""
    def __init__(self, read_limit=524288, text_limit=16000, counter=None):
        self.read_limit=read_limit;self.text_limit=text_limit;self.lock=threading.Lock()
        self.counter=counter
        self.reset(None)

    def reset(self, identity):
        """Discard another attempt's text and any partially written record."""
        self.identity=identity;self.offset=0;self.pending=b'';self.discard=False
        self.text='';self.streaming=False;self.previous=False;self.truncated=False
        self.reported_tokens=None;self.reported_output=None;self.response_id=None
        self.counted_text=None;self.visible_tokens=None

    def content(self, text, append=False):
        """Retain the latest reasoning block, keeping at most the visible tail."""
        if not isinstance(text,str):return
        full=self.text+text if append else text
        self.truncated=(self.truncated if append else False) or len(full)>self.text_limit
        self.text=full[-self.text_limit:];self.previous=False
        self.reported_tokens=None;self.reported_output=None;self.response_id=None

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
            has_thinking=False
            if isinstance(blocks,list):
                for block in blocks:
                    if isinstance(block,dict) and block.get('type')=='thinking':
                        self.content(block.get('thinking'));has_thinking=True
            self.streaming=False
            usage=message.get('usage') or {}
            if has_thinking and isinstance(usage,dict):
                for key,attr in [('reasoning','reported_tokens'),('output','reported_output')]:
                    value=usage.get(key)
                    if type(value) is int and value>=0:setattr(self,attr,value)
                self.response_id=message.get('responseId')

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
                        self.content('');self.previous=False;self.streaming=False;self.truncated=True
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
            if self.text!=self.counted_text:
                try:
                    from shadow_navigation import count
                    self.visible_tokens=(self.counter or count)(self.text) if self.text else 0
                except (OSError,ValueError,RuntimeError):self.visible_tokens=None
                self.counted_text=self.text
            return {'text':self.text,'streaming':running and self.streaming,
                    'previous':self.previous,'truncated':self.truncated,'source':'Pi reasoning output',
                    'visible_tokens_estimate':self.visible_tokens,
                    'reported_reasoning_tokens':self.reported_tokens,'reported_output_tokens':self.reported_output,
                    'response_id':self.response_id,'token_count_note':'Visible text uses the bundled tokenizer; reported usage is provider telemetry.'}
