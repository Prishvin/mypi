/** User instructions restart a bound atomic task; polling itself is read-only. */
const $=id=>document.getElementById(id),conversation=new URL(location.href).searchParams.get('conversation');
const endpoint=conversation?'/api/conversations/'+encodeURIComponent(conversation)+'/monitor/control':'/api/control';
let state=null,editor=null,instructionBinding=null,busy=false,token='';
async function request(method='GET',data){
 if(method==='POST'&&!token)token=(await fetch('/api/bootstrap').then(r=>r.json())).token;
 const response=await fetch(endpoint,{method,cache:'no-store',headers:{'Content-Type':'application/json','X-Local-Token':token},body:data?JSON.stringify(data):undefined});
 const result=await response.json();if(!response.ok)throw Error(result.error||'Task action failed');return result;
}
async function refresh(){
 if(busy)return;
 try{state=await request();const r=state.request;
  $('task-control-status').textContent=r?.status==='failed'?r.error:r?.status==='stopping'?'Stopping the current attempt safely…':r?.status==='starting'?'Starting a fresh attempt…':r?.status==='restarted'?'Fresh attempt started · '+r.todo:state.available?'Current task: '+state.todo:state.reason;
  for(const id of ['inject-task','edit-task'])$(id).disabled=!state.available||['stopping','starting'].includes(r?.status);
 }catch(error){$('task-control-status').textContent=error.message;}
}
async function restart(mode,prompt,binding){
 busy=true;for(const id of ['inject-task','edit-task','confirm-restart'])$(id).disabled=true;
 try{await request('POST',{revision:binding.revision,mode,prompt});$('task-prompt-dialog').close();$('task-instruction').value='';instructionBinding=null;$('task-control-status').textContent='Restart requested. Waiting for the saved checkpoint…';}
 catch(error){$('task-control-status').textContent=error.message;}finally{busy=false;$('confirm-restart').disabled=false;await refresh();}
}
$('task-instruction').oninput=()=>{if(!instructionBinding&&state?.available)instructionBinding={...state};if(!$('task-instruction').value)instructionBinding=null;};
$('inject-task').onclick=()=>{if(instructionBinding&&$('task-instruction').value.trim())restart('append',$('task-instruction').value,instructionBinding);};
$('edit-task').onclick=async()=>{await refresh();if(!state?.available)return;editor={...state};$('task-prompt-title').textContent='Restart '+state.todo;$('task-prompt').value=state.prompt;$('task-prompt-dialog').showModal();};
$('cancel-restart').onclick=()=>$('task-prompt-dialog').close();
$('confirm-restart').onclick=()=>{if(editor)restart('replace',$('task-prompt').value,editor);};
await refresh();setInterval(refresh,3000);
