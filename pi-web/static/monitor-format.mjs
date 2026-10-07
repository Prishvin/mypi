/** Formatting preserves unavailable measurements instead of displaying false zeros. */
export const number=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:1}):'—';
export const gib=v=>typeof v==='number'&&Number.isFinite(v)?(v/1024**3).toFixed(2)+' GiB':'—';
export function duration(v){if(typeof v!=='number'||!Number.isFinite(v))return '—';v=Math.max(0,v);return v<60?Math.floor(v)+'s':v<3600?Math.floor(v/60)+'m '+Math.floor(v%60)+'s':Math.floor(v/3600)+'h '+Math.floor(v%3600/60)+'m';}
export function phase(value){return ({chunk:'Reading prompt',reasoning:'Thinking',tool_call:'Writing tool call',answer:'Writing response'})[value]||value||'Idle';}
export function completion(done,total){return typeof done==='number'&&total>0?Math.max(0,Math.min(100,done/total*100)):0;}
export function testState(result,fresh){if(!result)return 'Not run';if(fresh===false)return 'Stale';return result.exit_code===0?'Passed':'Failed';}
