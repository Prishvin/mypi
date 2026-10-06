import * as render from './render.js';
import {conversationLink,queueState} from './navigation.js';
const $=id=>document.getElementById(id);let token='',selected=new URL(location.href).searchParams.get('conversation')||localStorage.getItem('pi-web-conversation'),current=null,listing=[],pending=false,lanOrigin='';
async function api(path,method='GET',data){const response=await fetch('/api/'+path,{method,headers:{'Content-Type':'application/json','X-Local-Token':token},body:data===undefined?undefined:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.error||response.statusText);return result;}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,6000);}
async function attempt(fn){try{return await fn();}catch(error){toast(error.message);}}
async function action(command,data={}){if(!selected)return;await api('conversations/'+selected+'/'+command,'POST',data);await refresh();}
function sidebar(){const query=$('search').value.toLowerCase();$('conversations').replaceChildren();for(const row of listing.filter(x=>x.title.toLowerCase().includes(query))){const b=render.el('button',row.title,'conversation'+(row.id===selected?' active':''));b.append(render.el('small',`${row.settings.mode==='pi'?'Pi agent':'Raw Qwen'}${row.busy?(row.status==='Queued'?' · Queued':' · Working'):''}`));b.onclick=()=>attempt(()=>select(row.id));$('conversations').append(b);}}
async function select(ident){selected=ident;localStorage.setItem('pi-web-conversation',ident);const url=new URL(location.href);url.searchParams.set('conversation',ident);history.replaceState(null,'',url);current=null;$('messages').replaceChildren();$('plan').dataset.signature='';$('question-card').dataset.id='';document.body.classList.remove('sidebar-open');$('settings').hidden=true;await refresh();}
function globalBusy(){const state=queueState(listing,selected);$('global-status').textContent=state.label;$('global-busy').classList.toggle('is-busy',state.busy);$('open-active').hidden=!state.active||state.active===selected;$('open-active').onclick=()=>attempt(()=>select(state.active));
 $('share').disabled=!selected;
 $('send').textContent=current?.dialog?.method==='input'?'Answer ↑':state.busy&&!current?.busy?'Send to queue ↑':'Send ↑';
 if(state.waiting)$('status').textContent='Queued · waiting for the active conversation to finish';}
async function create(){const row=await api('conversations','POST',{});await select(row.id);$('prompt').focus();}
function show(row){
  const scroll=$('scroll'),nearBottom=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<120;
  current=row;$('title').textContent=row.title;$('subtitle').textContent='Private project · '+row.id.slice(0,8);$('mode').value=row.settings.mode;
  const pi=row.settings.mode==='pi';$('mode-description').textContent=pi?'Tools, research & development workflow':'Direct model chat · no tools · separate model history';
  $('prompt').placeholder=pi?'Message Pi…':'Message Qwen directly…';$('composer-hint').textContent=pi?'Auto: chat, research, or plan a development task':'Direct chat. Switch to Pi for skills and development.';
  $('welcome').hidden=row.messages.length>0;render.messages($('messages'),row.messages,text=>attempt(()=>action('message',{text:'/remember '+text})),row.busy);
  render.plan($('plan'),row,(command,data)=>attempt(()=>action(command,data)));
  render.clarification($('question-card'),row.dialog,(id,value)=>attempt(()=>action('answer',{id,value})),row.messages.some(m=>m.kind==='clarification'&&m.dialogue_id===row.dialog?.id));
  $('status').textContent=row.status;$('metrics').textContent=(row.metrics_phase?'Last '+row.metrics_phase+' · ':'')+render.metrics(row.metrics,row.settings);
  if(row.execution_metrics)$('metrics').textContent+=' | Execution · '+render.metrics(row.execution_metrics,row.settings,false);
  if(row.review_metrics)$('metrics').textContent+=' | Review · '+render.metrics(row.review_metrics,row.settings,false);
  if(row.classification_metrics)$('metrics').textContent+=' | Classification · '+render.metrics(row.classification_metrics,row.settings,false);
  const canAnswer=row.dialog?.method==='input';
  $('stop').hidden=!row.busy;$('send').disabled=row.busy&&!canAnswer;$('mode').disabled=row.busy;$('delete').disabled=row.busy;
  if(canAnswer)$('composer-hint').textContent='Answer the clarification above. Your reply stays in this conversation.';
  $('settings-form').querySelectorAll('input,select,button').forEach(x=>x.disabled=row.busy);
  $('knowledge-text').replaceChildren(render.markdown(row.knowledge||'No saved knowledge yet. Use **/remember** after a useful answer.'));
  $('project-path').textContent='Project folder: '+row.project;
  $('activity-log').textContent=row.activity.map(x=>new Date(x.time*1000).toLocaleTimeString()+'  '+x.text).join('\n');$('run-log').textContent=row.run_log||'';
  if(nearBottom)scroll.scrollTop=scroll.scrollHeight;
}
async function refresh(){if(pending)return;pending=true;try{listing=await api('conversations');if(selected&&!listing.some(x=>x.id===selected)){selected=null;current=null;}
  if(selected)show(await api('conversations/'+selected));sidebar();globalBusy();}finally{pending=false;}}
$('new').onclick=()=>attempt(create);$('search').oninput=sidebar;$('menu').onclick=()=>document.body.classList.toggle('sidebar-open');
$('rename').onclick=()=>attempt(async()=>{if(!current)return;const title=prompt('Conversation name',current.title);if(title)await action('rename',{title});});
$('share').onclick=()=>attempt(async()=>{if(!selected)return;$('share-url').value=conversationLink(selected,location.origin,lanOrigin);$('share-dialog').showModal();$('share-url').select();});
$('share-copy').onclick=()=>attempt(async()=>{const input=$('share-url');input.select();
 if(navigator.clipboard&&isSecureContext){await navigator.clipboard.writeText(input.value);toast('Conversation link copied');}
 else if(document.execCommand('copy'))toast('Conversation link copied');
 else toast('Link selected. Copy it with your keyboard or touch menu.');});
$('delete').onclick=()=>attempt(async()=>{if(!current||!confirm('Delete this conversation? Its project files and development evidence will be retained.'))return;await api('conversations/'+selected,'DELETE');selected=null;await create();});
$('mode').onchange=()=>attempt(()=>action('settings',{mode:$('mode').value}));
$('settings-toggle').onclick=()=>{if(!current)return;$('settings').hidden=!$('settings').hidden;for(const [key,value] of Object.entries(current.settings)){const field=$('settings-form').elements.namedItem(key);if(field)field.value=value;}};
$('settings-form').onsubmit=e=>{e.preventDefault();attempt(async()=>{const values=Object.fromEntries(new FormData(e.target));for(const key of ['input_tokens','output_tokens','thinking_cap'])values[key]=Number(values[key]);await action('settings',values);$('settings').hidden=true;toast('Controls saved');});};
$('knowledge-toggle').onclick=()=>$('knowledge').hidden=!$('knowledge').hidden;$('activity-toggle').onclick=()=>$('activity-detail').hidden=!$('activity-detail').hidden;
$('stop').onclick=()=>attempt(()=>action('stop'));
$('composer').onsubmit=e=>{e.preventDefault();attempt(async()=>{const text=$('prompt').value.trim();if(!text)return;if(!selected)await create();
 if(current?.dialog?.method==='input')await action('answer',{id:current.dialog.id,value:text});else await action('message',{text});$('prompt').value='';});};
$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!current?.busy||current?.dialog?.method==='input')$('composer').requestSubmit();}};
for(const b of document.querySelectorAll('[data-prompt]'))b.onclick=()=>{$('prompt').value=b.dataset.prompt;$('prompt').focus();};
await attempt(async()=>{try{lanOrigin=(await fetch('/network.json').then(r=>r.json())).lan_base_url||'';}catch{}
 const boot=await api('bootstrap');token=boot.token;listing=boot.conversations;
 if(new URL(location.href).searchParams.has('conversation')&&!listing.some(x=>x.id===selected)){selected=null;sidebar();globalBusy();$('title').textContent='Conversation unavailable';toast('This conversation link was deleted or is unavailable.');return;}
 if(!selected||!listing.some(x=>x.id===selected))selected=listing[0]?.id;
  if(!selected)await create();else await select(selected);});
setInterval(()=>attempt(refresh),1200);
