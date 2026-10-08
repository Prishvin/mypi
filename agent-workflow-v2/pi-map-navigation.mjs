/** Turn incomplete section addresses into an explicit, bounded index lookup. */
export function sectionLookup(action,query,sha256){
 return action==='architecture-section'&&Boolean(query?.trim())&&!sha256;
}

export function navigationReply(params,stdout){
 if(!sectionLookup(params.action,params.query,params.sha256))return stdout;
 const result=JSON.parse(stdout);
 const calls=(result.matches||[]).filter(row=>row.kind==='section').map(row=>({
  action:'architecture-section',query:row.id,sha256:result.source_sha256,offset:0
 }));
 return JSON.stringify({...result,requested_action:'architecture-section',action:'architecture-search',
  section_read:false,query:params.query,
  note:'No source hash was supplied, so this call looked up matching map entries only. '+
       'Choose a next_call to read its section; no section text has been read. '+
       'If there are no matches, use a shorter filename/keyword or the architecture index.',
  next_calls:calls,...(result.more?{next_search:{action:'architecture-search',query:params.query,offset:result.next_offset}}:{})});
}
