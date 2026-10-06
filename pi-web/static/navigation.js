/** Durable LAN conversation links and truthful queue labels, without model calls. */
export function conversationLink(id,origin,lanOrigin){
  if(!/^[a-f0-9]{24}$/.test(id))throw new Error('Invalid conversation link');
  const local=['localhost','127.0.0.1'].includes(new URL(origin).hostname);
  const url=new URL(local&&lanOrigin?lanOrigin:origin);
  url.pathname='/';url.search='';url.hash='';url.searchParams.set('conversation',id);
  return url.href;
}

export function queueState(rows,selected){
  const busy=rows.filter(row=>row.busy),active=busy.find(row=>row.status!=='Queued');
  if(!busy.length)return {busy:false,label:'Assistant ready · no active UI queries',active:null,queued:0,waiting:false};
  const queued=busy.filter(row=>row.status==='Queued').length;
  const self=busy.find(row=>row.id===selected),waiting=self?.status==='Queued';
  let label=active?'Assistant busy · '+active.title+' · '+active.status:'Assistant busy · starting the next query';
  if(queued)label+=' · '+queued+' queued';
  if(waiting)label+=' · Your query is waiting';
  return {busy:true,label,active:active?.id||null,queued,waiting};
}
