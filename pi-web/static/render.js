import {marked} from './marked.js';
const allowed=new Set('P BR STRONG EM DEL CODE PRE UL OL LI BLOCKQUOTE H1 H2 H3 H4 HR TABLE THEAD TBODY TR TH TD A'.split(' '));
export function markdown(text){
  const template=document.createElement('template');template.innerHTML=marked.parse(text||'',{async:false});
  const fragment=document.createDocumentFragment();
  function clean(source,target){for(const child of source.childNodes){
    if(child.nodeType===Node.TEXT_NODE){target.append(document.createTextNode(child.textContent));continue;}
    if(child.nodeType!==Node.ELEMENT_NODE)continue;
    if(['SCRIPT','STYLE','IFRAME','OBJECT','SVG','MATH','IMG'].includes(child.tagName))continue;
    if(!allowed.has(child.tagName)){clean(child,target);continue;}
    const node=document.createElement(child.tagName.toLowerCase());
    if(child.tagName==='A'){
      try{const url=new URL(child.getAttribute('href'));if(['http:','https:'].includes(url.protocol)){node.href=url.href;node.target='_blank';node.rel='noopener noreferrer';}}catch{}
    }
    clean(child,node);target.append(node);
  }}clean(template.content,fragment);return fragment;
}
export const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
export function clarification(container,dialog,answer,questionTracked=false){
  container.hidden=!dialog;
  if(!dialog){container.replaceChildren();container.dataset.id='';return;}
  if(container.dataset.id===dialog.id)return;
  container.dataset.id=dialog.id;container.replaceChildren();
  container.append(el('h3',questionTracked?'Reply to clarification':'Clarification'));
  if(!questionTracked)container.append(el('p',dialog.title||dialog.message||'Please clarify your request.'));
  const controls=el('div',undefined,'dialog-actions');
  const pause=el('button','Pause');pause.onclick=()=>answer(dialog.id,null);controls.append(pause);
  if(dialog.method==='select'){
    const select=el('select');select.setAttribute('aria-label','Clarification answer');
    for(const value of dialog.options||[]){const option=el('option',value);option.value=value;select.append(option);}
    container.append(select);const submit=el('button','Continue','primary');submit.onclick=()=>answer(dialog.id,select.value);controls.append(submit);
  }else if(dialog.method==='confirm'){
    for(const [label,value] of [['No',false],['Yes',true]]){const button=el('button',label,label==='Yes'?'primary':'');button.onclick=()=>answer(dialog.id,value);controls.append(button);}
  }else container.append(el('p','Reply in the message box below.','muted'));
  container.append(controls);
}
export function messages(container,rows,remember,busy){
  const existing=new Map([...container.children].map(node=>[node.dataset.id,node]));
  for(const row of rows){
    if(row.role==='assistant' && !row.text && !row.thinking)continue;
    let node=existing.get(row.id);
    if(!node){node=el('article',undefined,'message '+row.role);node.dataset.id=row.id;container.append(node);}
    const signature=JSON.stringify([row.text,row.thinking,busy]);if(node.dataset.signature===signature)continue;
    node.dataset.signature=signature;const wasOpen=node.querySelector('details')?.open;node.replaceChildren();
    if(row.kind==='clarification')node.append(el('div','Pi · clarification','label'));
    else if(row.role!=='notice')node.append(el('div',row.role==='user'?'You':row.mode==='raw'?'Qwen · direct':row.phase==='architect'?'Pi · planner':'Pi · local Qwen','label'));
    if(row.thinking){const detail=el('details');detail.open=!!wasOpen;detail.append(el('summary','Thinking'),el('div',row.thinking));node.append(detail);}
    const body=el('div');if(row.role==='user')body.textContent=row.text;else body.append(markdown(row.text));node.append(body);
    if(row.role==='assistant' && row.text && row.mode==='pi'){
      const button=el('button','Remember essentials','remember');button.disabled=busy;button.onclick=()=>remember(row.text);node.append(button);
    }
  }
}
export function plan(container,row,action){
  container.hidden=!row.plan_data && !row.pending_plan && !row.pending_route;
  const signature=JSON.stringify([row.plan_data,row.pending_plan,row.pending_route,row.busy,row.run_dir,row['state.json'],row['final-review/review.json']]);
  if(container.dataset.signature===signature)return;container.dataset.signature=signature;container.replaceChildren();
  if(row.pending_route){container.append(el('h2','Request intake'));
    if(!row.busy){const b=el('button','Resume intake','primary');b.onclick=()=>action('message',{text:'/resume-request'});container.append(b);}return;}
  if(row.pending_plan && !row.plan_data){container.append(el('h2','Planning in progress'));
    if(!row.busy){const b=el('button','Resume planning','primary');b.onclick=()=>action('message',{text:'/resume-planning'});container.append(b);}return;}
  if(!row.plan_data)return;
  container.append(el('h2',row.plan_data.title||'Development plan'));
  if(row.run_dir){const link=el('a','Open granular live todo dashboard','monitor-link');link.href='/monitor?conversation='+encodeURIComponent(row.id);link.target='_blank';link.rel='noopener';container.append(link);}
  for(const task of row.plan_data.tasks||[]){const node=el('div',undefined,'plan-task');
    node.append(el('strong',(task.status==='done'?'✓ ':'○ ')+task.id+' · '+task.goal));
    const details=el('details');details.append(el('summary','Scope, acceptance, tests & context'),el('pre',JSON.stringify({files:task.files,acceptance:task.acceptance,tests:task.tests,context:task.context},null,2)));node.append(details);container.append(node);}
  const review=row['final-review/review.json'];
  if(review){
    const panel=el('section',undefined,'review');
    panel.append(el('h3',review.verdict==='clean'?'✓ Final review passed':'Reviewer follow-up'),el('p',review.summary));
    for(const finding of review.findings||[])panel.append(el('p',finding.observation));
    const evidence=el('details');evidence.append(el('summary','Review evidence'),el('pre',JSON.stringify(review,null,2)));
    panel.append(evidence);container.append(panel);
  }
  const controls=el('div',undefined,'plan-actions');
  const complete=row['state.json']?.status==='complete' && !!row['final-review/result.json']?.passed;
  for(const [label,command] of [[complete?'Completed':row.run_dir?'Resume run':'Run plan','execute'],['Replan from evidence','replan']]){
    const b=el('button',label,command==='execute'?'primary':'');b.disabled=row.busy||(command==='execute'&&complete)||(command==='replan'&&row['state.json']?.status!=='needs_replan');b.onclick=()=>action(command,{});controls.append(b);
  }
  if(row['final-review/review.json']?.verdict==='followup'){const b=el('button','Use reviewer follow-up');b.disabled=row.busy;b.onclick=()=>action('followup',{});controls.append(b);}
  container.append(controls);
}
export function metrics(data,cfg,limits=true){
  const pieces=limits?[`96k capacity`,`input ≤ ${cfg.input_tokens.toLocaleString()}`,`output ≤ ${cfg.output_tokens.toLocaleString()}`,`thinking ${cfg.thinking==='off'?'off':cfg.thinking_cap||'uncapped'}`]:[];
  if(data){const native=data.native_requests?.at(-1);if(data.wall_seconds)pieces.push(`${data.wall_seconds.toFixed(1)}s`);
    pieces.push(`${data.input_tokens_sum||0} input / ${data.output_tokens_sum||0} output tokens`);
    if(native?.decode_tok_s)pieces.push(`${native.decode_tok_s.toFixed(1)} tok/s`);
    if(native?.ttft_s)pieces.push(`first token ${native.ttft_s.toFixed(1)}s`);
    if(data.server_rss_peak_sampled_bytes)pieces.push(`RAM RSS ${(data.server_rss_peak_sampled_bytes/2**30).toFixed(1)} GiB`);
    else if(native?.active_memory_bytes)pieces.push(`MLX allocation ${(native.active_memory_bytes/2**30).toFixed(1)} GiB`);
  }return pieces.join(' · ');
}
