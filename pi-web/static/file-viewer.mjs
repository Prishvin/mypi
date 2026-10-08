/** Fetch only the selected declared project file and render source as plain text. */
const params=new URL(location.href).searchParams,conversation=params.get('conversation');
const query=new URLSearchParams({run:params.get('run')||'',path:params.get('path')||''});
const endpoint=conversation?'/api/conversations/'+encodeURIComponent(conversation)+'/monitor/file':'/api/file';
document.getElementById('back').href=conversation?'/monitor?conversation='+encodeURIComponent(conversation):'/';
document.getElementById('filename').textContent=params.get('path')||'Project file';
let pending=false;
async function refresh(){
 if(pending)return;pending=true;const status=document.getElementById('file-status'),source=document.getElementById('source');
 status.textContent='Loading current file…';
 try{const response=await fetch(endpoint+'?'+query,{cache:'no-store'}),file=await response.json();
  if(!response.ok)throw Error(file.error||'File unavailable');
  source.textContent=file.content.split('\n').map((line,i)=>String(i+1).padStart(4)+'  '+line).join('\n');
  status.textContent='Read-only · current file on disk · '+file.preview_bytes.toLocaleString()+' bytes'+(file.truncated?' · preview limited to 256 KiB':'');
 }catch(error){source.textContent='';status.textContent=error.message;}finally{pending=false;}
}
document.getElementById('reload').onclick=refresh;await refresh();
