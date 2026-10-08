/** Preserve small, still-current source observations without replaying tool turns. */
import {readFileSync,writeFileSync,realpathSync,statSync} from 'node:fs';
import {join,resolve,relative,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';

const bytes=value=>Buffer.byteLength(JSON.stringify(value),'utf8');
const digest=raw=>createHash('sha256').update(raw).digest('hex');
const cachePath=session=>join(session,'retrieved-source-memory.json');

function current(project,row) {
  if(!project||typeof row?.path!=='string'||typeof row.source!=='string'||!row.source||
      bytes(row)>14000||!/^([a-f0-9]{64})$/.test(row.sha256||'')||
      (row.symbol!==undefined&&typeof row.symbol!=='string'))return null;
  try {
    const root=realpathSync(project),file=realpathSync(resolve(root,row.path));
    const path=relative(root,file);
    if(path==='..'||path.startsWith('../')||isAbsolute(path)||!statSync(file).isFile()||
        statSync(file).size>1048576||digest(readFileSync(file))!==row.sha256)return null;
    return {path,sha256:row.sha256,...(row.symbol?{symbol:row.symbol}:{}),
      ...(Number.isInteger(row.next_offset)?{next_offset:row.next_offset}:{}),
      more:row.more===true,source:row.source};
  } catch {return null;}
}

function load(session) {
  try {
    const text=readFileSync(cachePath(session),'utf8');
    if(Buffer.byteLength(text)>24576)return [];
    const rows=JSON.parse(text);return Array.isArray(rows)?rows.slice(0,8):[];
  } catch {return [];}
}

export function rememberSource(session,project,text) {
  // Optional context memory must never turn a successful retrieval into a failure.
  try {
    const value=JSON.parse(text),records=Array.isArray(value.symbols)?value.symbols:[value];
    const rows=load(session),key=row=>JSON.stringify([row.path,row.symbol,row.next_offset]);
    for(const record of records) {
      const row=current(project,record);if(!row)continue;
      const old=rows.findIndex(entry=>key(entry)===key(row));if(old>=0)rows.splice(old,1);
      rows.unshift(row);
    }
    while(rows.length>8||bytes(rows)>24576)rows.pop();
    writeFileSync(cachePath(session),JSON.stringify(rows));
  } catch {}
}

export function recallSource(session,project,maxBytes=6000) {
  const memory={entries:[],invalidated:0,omitted:0};
  for(const stored of load(session)) {
    const row=current(project,stored);
    if(!row){memory.invalidated++;continue;}
    if(bytes([...memory.entries,row])>maxBytes){memory.omitted++;continue;}
    memory.entries.push(row);
  }
  return memory;
}

export function attachSourceMemory(summary,memory,limit=12000) {
  const split=summary.indexOf('\n'),prefix=summary.slice(0,split+1);
  const data=JSON.parse(summary.slice(split+1));
  const stats={retained:0,invalidated:memory.invalidated,omitted:memory.omitted+memory.entries.length};
  if(!memory.entries.length)return {summary,stats};
  const entries=[];
  data.retrieved_sources={note:'Previously retrieved project data; hashes verified at this checkpoint. Line labels are navigation, not edit text. Any subsequent file edit can invalidate these excerpts.',entries};
  if((prefix+JSON.stringify(data)).length>limit)return {summary,stats};
  for(const row of memory.entries) {
    entries.push(row);
    if((prefix+JSON.stringify(data)).length>limit)entries.pop();
    else {stats.retained++;stats.omitted--;}
  }
  data.retrieved_sources.omitted=stats.omitted;
  let result=prefix+JSON.stringify(data);
  // The omission counter itself also consumes the fixed handoff allowance.
  while(result.length>limit&&entries.length){entries.pop();stats.retained--;stats.omitted++;
    data.retrieved_sources.omitted=stats.omitted;result=prefix+JSON.stringify(data);}
  return {summary:result.length<=limit?result:summary,stats};
}
