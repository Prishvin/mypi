/** Hooks confined to this explicit workflow; Codex configuration stays separate. */
import { readFileSync, appendFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import {domainInstructions} from './pi-domain-skills.mjs';
import {failedEditEvidence} from './pi-edit-recovery.mjs';
import {requireThinkingCaps} from './pi-thinking-cap.mjs';

export function applies(model) { return model?.provider === 'local-qwen-workflow'; }

export function active(model) {
  return applies(model) || (model?.provider === 'openai' &&
    ((process.env.QWEN_WORKFLOW_PLANNER === 'chatgpt' && ['architect','research','intake','reviewer','memory'].includes(process.env.QWEN_WORKFLOW_ROLE)) ||
     (process.env.QWEN_WORKFLOW_EXECUTOR === 'chatgpt' && process.env.QWEN_WORKFLOW_ROLE === 'code')));
}

export function installPromptHooks(pi, home) {
  const runtime = process.env.QWEN_WORKFLOW_RUNTIME || home;
  pi.on('before_provider_request', async (event, ctx) => {
    if (active(ctx.model) && ctx.model.provider === 'openai') {
      const payload={...event.payload, max_output_tokens: Number(process.env.QWEN_WORKFLOW_OUTPUT_BUDGET || 32768)};
      if(ctx.model.id==='gpt-6.1-sol' && process.env.QWEN_WORKFLOW_REASONING==='xhigh' && payload.reasoning?.effort!=='xhigh')
        throw new Error('GPT-6.1 Sol xhigh was not preserved by the model configuration');
      const session=process.env.QWEN_WORKFLOW_SESSION;
      if(session && existsSync(session))appendFileSync(join(session,'provider-controls.jsonl'),JSON.stringify({
        model:ctx.model.id,role:process.env.QWEN_WORKFLOW_ROLE,reasoning_effort:payload.reasoning?.effort,
        max_output_tokens:payload.max_output_tokens,epoch:Date.now()/1000})+'\n');
      return payload;
    }
    if (!applies(ctx.model) || !process.env.QWEN_WORKFLOW_PROJECT) return;
    const smoke = process.env.QWEN_WORKFLOW_SMOKE === '1';
    const thinking = !smoke && process.env.QWEN_WORKFLOW_THINKING !== 'off';
    const effort = process.env.QWEN_WORKFLOW_REASONING || 'xhigh';
    const policy = process.env.QWEN_WORKFLOW_HISTORY_POLICY || 'auto';
    if (!['auto','off'].includes(policy)) throw new Error('Invalid thinking-history policy');
    const messages = policy === 'off' ? event.payload.messages.map(message => message.role === 'assistant' ?
      {...message,reasoning_content:''} : message) : event.payload.messages;
    const payload = { ...event.payload, temperature: smoke ? 0 : (thinking ? 1 : 0.7),
      top_p: thinking ? 0.95 : 0.8, top_k: process.env.QWEN_WORKFLOW_MODEL_VARIANT === 'gemma' ? 64 : 20,
      presence_penalty: 0, enable_thinking: thinking, suppress_stats_footer: true,
      messages,
      ...(smoke ? { max_tokens: Number(process.env.QWEN_WORKFLOW_SMOKE_MAX_TOKENS || 512) } : {}),
      reasoning_effort: effort,
      metadata: { ...(event.payload.metadata || {}), client: 'pi',
        mtplx_request_id: `${process.env.QWEN_WORKFLOW_SESSION.split('/').at(-1)}-${Date.now()}` },
      chat_template_kwargs: { ...(event.payload.chat_template_kwargs || {}), enable_thinking: thinking,
        reasoning_effort: effort } };
    process.env.QWEN_WORKFLOW_CURRENT_REQUEST_ID = payload.metadata.mtplx_request_id;
    // MTPLX auto preserves the active Qwen tool chain without a forced template override.
    if (policy === 'off') payload.chat_template_kwargs.preserve_thinking = false;
    if (process.env.QWEN_WORKFLOW_MODEL_VARIANT === 'gemma') {
      delete payload.reasoning_effort;
      delete payload.chat_template_kwargs.reasoning_effort;
    }
    for (const [name, field, maximum] of [['QWEN_WORKFLOW_TEMPERATURE', 'temperature', 2],
      ['QWEN_WORKFLOW_TOP_P', 'top_p', 1]]) {
      if (process.env[name] === undefined) continue;
      const value = Number(process.env[name]);
      if (!Number.isFinite(value) || value < 0 || value > maximum || (field === 'top_p' && value === 0))
        throw new Error(`Invalid sampling override ${name}`);
      payload[field] = value;
    }
    if (process.env.QWEN_WORKFLOW_SEED !== undefined) {
      const seed=Number(process.env.QWEN_WORKFLOW_SEED);
      if (!Number.isInteger(seed) || seed<0 || seed>4294967295) throw new Error('Invalid sampling seed');
      payload.seed=seed;
    }
    const configuredBudget = process.env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS;
    const configuredOutput = process.env.QWEN_WORKFLOW_OUTPUT_BUDGET;
    if (!smoke && configuredOutput !== undefined) {
      const limit = Number(configuredOutput);
      if (!Number.isInteger(limit) || limit < 512 || limit > 32768) throw new Error('Invalid total-output token cap');
      delete payload.max_tokens;
      payload.max_completion_tokens = limit;
    }
    if (thinking && configuredBudget !== undefined) {
      const budget = Number(configuredBudget);
      if (!Number.isInteger(budget) || budget < 0 || budget > 32768) throw new Error('Invalid thinking-token budget');
      if (configuredOutput !== undefined && budget > Number(configuredOutput) - 2048) throw new Error('Thinking cap leaves insufficient edit/tool-call output');
      if (['27b','flash'].includes(process.env.QWEN_WORKFLOW_MODEL_VARIANT)) payload.reasoning_budget_tokens = budget;
    }
    if (thinking && process.env.QWEN_WORKFLOW_MODEL_VARIANT === 'quality') {
      await requireThinkingCaps();
      payload.metadata.pi_thinking_cap = configuredBudget === undefined ? 0 : Number(configuredBudget);
    }
    if (process.env.QWEN_WORKFLOW_REQUEST_LOG) appendFileSync(process.env.QWEN_WORKFLOW_REQUEST_LOG, JSON.stringify(payload) + '\n');
    if (process.env.QWEN_WORKFLOW_INPUT_BUDGET) {
      const request = join(process.env.QWEN_WORKFLOW_SESSION, 'request-budget.json');
      writeFileSync(request, JSON.stringify(payload));
      const result = await pi.exec(join(home, '.venv/bin/python'), [join(runtime, 'token_budget.py'), request,
        '--limit', process.env.QWEN_WORKFLOW_INPUT_BUDGET], { timeout: 10000 });
      writeFileSync(join(process.env.QWEN_WORKFLOW_SESSION, 'request-budget-result.json'), result.stdout);
      if (result.code) {
        ctx.abort();
        throw new Error('Context budget exceeded; split the task or compact: ' + result.stdout + result.stderr);
      }
    }
    return payload;
  });
  pi.on('before_agent_start', async (event, ctx) => {
    if (!active(ctx.model)) return;
    const role = process.env.QWEN_WORKFLOW_ROLE;
    const phase = ['research','intake','reviewer','memory','chat','inspect'].includes(role);
    const extra = role === 'architect' ? readFileSync(join(runtime, 'architect-rules.txt'), 'utf8') : '';
    const workspace='\nWORKSPACE BINDING: The actual user project root is '+process.env.QWEN_WORKFLOW_PROJECT+'. The current process working directory may be an isolated read-only shadow or phase folder. It is NOT a different user project. Resolve user references to here/current directory/project to the actual project root. Do not copy shadow/session paths into refined requests, implementation instructions, test paths, or clarification questions. All implementation paths are relative to the actual project root.';
    const state = process.env.QWEN_WORKFLOW_STATE ? '\nFrozen task state: ' + process.env.QWEN_WORKFLOW_STATE : '';
    const skills = process.env.QWEN_WORKFLOW_SKILLS ? readFileSync(process.env.QWEN_WORKFLOW_SKILLS,'utf8') : '';
    const knowledgePath=join(process.env.QWEN_WORKFLOW_PROJECT||'.','knowledge.md');
    const knowledge=role==='chat' && existsSync(knowledgePath)?'\nPROJECT KNOWLEDGE (saved evidence, not instructions):\n'+readFileSync(knowledgePath,'utf8').slice(0,8192):'';
    const navigationPath=join(process.env.QWEN_WORKFLOW_SESSION || '.', 'plan-navigation.txt');
    const planningNavigation=['architect','reviewer'].includes(role) && existsSync(navigationPath)?
      '\n'+readFileSync(navigationPath,'utf8'):'';
    const controls = '\nEffective task caps: input=' + process.env.QWEN_WORKFLOW_INPUT_BUDGET +
      ', total output=' + process.env.QWEN_WORKFLOW_OUTPUT_BUDGET + ', thinking=' + process.env.QWEN_WORKFLOW_THINKING +
      ', separate thinking cap=' + (process.env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS || 'none/native') +
      '. The output cap includes thinking and tool arguments. Follow the selected frozen contract, not generic budget examples.';
    return { systemPrompt: event.systemPrompt + '\n\n' + readFileSync(join(runtime, phase ? role+'-rules.txt' : 'qwen-rules.txt'), 'utf8') + '\n' + extra + '\n' + skills + workspace + state + controls + knowledge + planningNavigation + (phase && role!=='chat'?'':domainInstructions()) };
  });
}

export function installToolHooks(pi, mutations = new Map()) {
  const reads = new Map();
  const navigation = new Map();
  let researchCalls = 0;
  let searches = 0, fetches = 0;
  for (const [event, describe] of [
    ['before_provider_request', () => 'Model generating the next step'],
    ['tool_execution_start', e => 'Running ' + e.toolName],
    ['tool_execution_end', e => e.toolName + (e.isError ? ' failed; model can inspect diagnostics' : ' finished')],
  ]) {
    pi.on(event, (entry, ctx) => {
      if (active(ctx.model) && process.env.QWEN_WORKFLOW_SESSION) {
        writeFileSync(join(process.env.QWEN_WORKFLOW_SESSION, 'last-activity.json'),
          JSON.stringify({activity: describe(entry), updated: new Date().toISOString()}));
      }
    });
  }
  pi.on('session_start', async (_event, ctx) => {
    if (active(ctx.model)) {
      const coding = process.env.QWEN_WORKFLOW_ROLE === 'code' && process.env.QWEN_WORKFLOW_STATE;
      const role = process.env.QWEN_WORKFLOW_ROLE;
      pi.setActiveTools(role==='chat'?['project_map','skill_use','skill_read']:role==='inspect'?['project_map','source_query','skill_use','skill_read']:role==='memory'?['memory_store']:role==='intake'?['intake_store']:role==='reviewer'?['project_map','plan_store','review_store']:role==='research'?['project_map','web_research','skill_use','knowledge_store']:
        coding ? ['project_map', 'source_query', 'edit', 'write', 'workflow_test', 'web_research', 'skill_read','skill_use'] : ['project_map', 'plan_store', 'web_research', 'skill_read','skill_use']);
    }
  });
  pi.on('tool_call', async (event, ctx) => {
    if (!active(ctx.model)) return;
    const role=process.env.QWEN_WORKFLOW_ROLE;
    const phaseTools={chat:['project_map','skill_use','skill_read'],inspect:['project_map','source_query','skill_use','skill_read'],memory:['memory_store'],intake:['intake_store'],research:['project_map','web_research','skill_use','knowledge_store'],reviewer:['project_map','plan_store','review_store']};
    if (phaseTools[role] && !phaseTools[role].includes(event.toolName))
      return {block:true,reason:'This initial phase cannot read or edit implementation or run project commands'};
    if (role==='research' && event.toolName==='project_map' && !['architecture','architecture-section','architecture-search','sync-check'].includes(event.input?.action))
      return {block:true,reason:'Research reads only the brief architecture map; no source catalogue needed'};
    if (role==='inspect' && event.toolName==='project_map' && event.input?.action==='gate')
      return {block:true,reason:'Inspection has no execution contract or completion gate'};
    if (role==='research' && event.toolName==='web_research' && ['search','fetch'].includes(event.input?.action))
      return {block:true,reason:'Use skill_use prepare/run with duckduckgo-search or public-page-fetch so executable skills are exercised'};
    if (['research','chat','inspect'].includes(role) && event.toolName==='skill_use' && event.input?.action==='run') {
      if (['duckduckgo-search','duckduckgo-research'].includes(event.input.name) && ++searches>3)
        return {block:true,reason:'Three search limit reached; record missing evidence and save the brief'};
      if (event.input.name==='duckduckgo-research' && (fetches+=2)>6)
        return {block:true,reason:'Six page-fetch limit reached; use collected evidence'};
      if (event.input.name==='public-page-fetch' && ++fetches>6)
        return {block:true,reason:'Six fetch limit reached; use stored excerpts and save the brief'};
    }
    if (event.toolName === 'web_research' && event.input?.action !== 'brief') {
      researchCalls++;
      if (researchCalls > 8) {
        if (researchCalls > 10) ctx.abort();
        return {block:true,reason:'Research budget reached. Distill fetched evidence into one brief; record missing evidence rather than continuing open-ended browsing.'};
      }
    }
    if (['project_map', 'source_query'].includes(event.toolName) && event.input?.action !== 'gate') {
      let snapshot = '';
      try { snapshot = JSON.parse(readFileSync(join(process.env.QWEN_WORKFLOW_SHADOW, 'manifest.json'), 'utf8')).snapshot; } catch {}
      if (process.env.QWEN_WORKFLOW_ROLE === 'code') {
        const total = (navigation.get(snapshot) || 0) + 1;
        navigation.set(snapshot, total);
        if (total > 12) {
          if (total > 14) ctx.abort();
          return { block: true, reason: 'Navigation budget reached for unchanged source. Implement from collected evidence and run workflow_test; split the task if evidence is insufficient.' };
        }
      }
      const key = snapshot + event.toolName + JSON.stringify(event.input);
      const count = (reads.get(key) || 0) + 1;
      reads.set(key, count);
      if (count > 3) {
        ctx.abort();
        return { block: true, reason: 'Repeated identical retrieval detected. Stop, review evidence, then resume a focused task.' };
      }
    }
    if (process.env.QWEN_WORKFLOW_ROLE === 'architect' && !['project_map', 'plan_store', 'web_research', 'skill_read','skill_use'].includes(event.toolName)) {
      return { block: true, reason: 'Architect mode can inspect interfaces and save plans only' };
    }
    const architectureEdit = event.toolName === 'skill_use' && event.input?.name === 'architecture-update' && event.input?.action === 'run';
    if (['edit', 'write'].includes(event.toolName) || architectureEdit) {
      const state = process.env.QWEN_WORKFLOW_STATE;
      if (!state) return { block: true, reason: 'Start a frozen task contract before editing' };
      const contract = JSON.parse(readFileSync(state, 'utf8'));
      const target = architectureEdit ? resolve(contract.before.root, 'architecture.md') : resolve(ctx.cwd, event.input.path || '');
      if (!contract.task.files.some(path => resolve(contract.before.root, path) === target)) {
        return { block: true, reason: 'File is outside the atomic task scope' };
      }
      if (!architectureEdit && target === resolve(contract.before.root, 'architecture.md')) {
        return {block:true,reason:'Preserve authored architecture: use architecture-update insert/append_section; interface metadata refresh is automatic'};
      }
      if (mutations.has(target)) {
        return { block: true, reason: 'An edit of this file is still running. Batch disjoint replacements in one edit call, or wait for its shadow refresh.' };
      }
      mutations.set(target, event.toolCallId);
    }
  });
}

export function installRefreshHooks(pi, python, cli, scopeArgs, mutations = new Map()) {
  let pending = Promise.resolve();
  const refresh = ctx => {
    const output = process.env.QWEN_WORKFLOW_SHADOW;
    if (!output) throw new Error('Shadow path missing');
    pending = pending.catch(() => {}).then(async () => {
      const result = await pi.exec(python, [cli, ...scopeArgs(process.env.QWEN_WORKFLOW_PROJECT || ctx.cwd),
        'refresh', '--output', output, ...(process.env.QWEN_WORKFLOW_STATE ? ['--state', process.env.QWEN_WORKFLOW_STATE] : [])], { timeout: 30000 });
      if (result.code) throw new Error(result.stderr || result.stdout);
      return JSON.parse(result.stdout);
    });
    return pending;
  };
  pi.on('tool_result', async (event, ctx) => {
    const role=process.env.QWEN_WORKFLOW_ROLE;
    if (active(ctx.model) && ['research','intake','reviewer','memory'].includes(role) && !event.isError && event.details?.phase===role &&
        event.details?.output===process.env.QWEN_WORKFLOW_PHASE_OUTPUT) {
      const output=process.env.QWEN_WORKFLOW_PHASE_OUTPUT;
      writeFileSync(join(process.env.QWEN_WORKFLOW_SESSION,role+'-stop.json'),JSON.stringify({output,
        sha256:createHash('sha256').update(readFileSync(output)).digest('hex'),reason:'Verified '+role+' draft saved'}));
      ctx.abort();
      return {content:event.content,details:{...event.details,acceptedPhaseStop:true}};
    }
    if (active(ctx.model) && process.env.QWEN_WORKFLOW_ROLE === 'architect' &&
        event.toolName === 'plan_store' && !event.isError &&
        event.details?.plan === process.env.QWEN_WORKFLOW_PLAN) {
      const plan=process.env.QWEN_WORKFLOW_PLAN;
      const session=process.env.QWEN_WORKFLOW_SESSION;
      if (!plan || !session) return;
      const sha256=createHash('sha256').update(readFileSync(plan)).digest('hex');
      writeFileSync(join(session,'planning-stop.json'),JSON.stringify({plan,sha256,
        reason:'Validated structured plan saved; deterministic runner takes over',finished_epoch:Date.now()/1000}));
      ctx.abort();
      return {content:event.content,details:{...event.details,acceptedPlanningStop:true}};
    }
    if (applies(ctx.model) && process.env.QWEN_WORKFLOW_ROLE === 'code' &&
        process.env.QWEN_WORKFLOW_STOP_AFTER_PASS === '1' && event.toolName === 'workflow_test' &&
        !event.isError && event.details?.testsPassed === true && event.details?.gatePassed === true) {
      const state = process.env.QWEN_WORKFLOW_STATE;
      if (!state) return;
      await refresh(ctx);
      const result = await pi.exec(python, [cli, 'check', '--state', state], { timeout: 30000 });
      if (result.code !== 0) return;
      const gate = JSON.parse(result.stdout);
      if (!gate.passed) return;
      const session = process.env.QWEN_WORKFLOW_SESSION;
      if (session) writeFileSync(join(session, 'completion-stop.json'), JSON.stringify({
        reason: 'Fresh frozen tests and atomic gate passed; stop before another provider request',
        finished_epoch: Date.now() / 1000, shadow_snapshot: gate.shadow_snapshot,
      }, null, 2));
      ctx.abort();
      return {content: [...event.content, {type:'text', text:'Atomic task verified; execution finished.'}],
        details: {...event.details, acceptedCompletion:true}};
    }
    const architectureEdit = event.toolName === 'skill_use' &&
      (event.input?.name || event.details?.skill) === 'architecture-update' &&
      (event.input?.action || event.details?.action) === 'run';
    if (!active(ctx.model) || (!['edit', 'write'].includes(event.toolName) && !architectureEdit)) return;
    try {
      const summary = await refresh(ctx);
      if (applies(ctx.model) && process.env.QWEN_WORKFLOW_ROLE === 'code' &&
          process.env.QWEN_WORKFLOW_STOP_AFTER_PASS === '1' && !event.isError && process.env.QWEN_WORKFLOW_STATE) {
        const state = process.env.QWEN_WORKFLOW_STATE;
        const tests = await pi.exec(python, [cli, 'test', '--state', state], { timeout:310000 });
        const checked = await pi.exec(python, [cli, 'check', '--state', state], { timeout:30000 });
        const gate = JSON.parse(checked.stdout);
        const accepted = tests.code === 0 && checked.code === 0 && gate.passed;
        const results = JSON.parse(tests.stdout).results || [];
        const failed = results.filter(row => row.exit_code);
        const index = failed.map(row => ({log:row.log,exit_code:row.exit_code,
          failing_tests:readFileSync(row.log,'utf8').split('\n').filter(line => /^(?:not ok|[✖×])/.test(line)).map(line=>line.slice(0,300))}));
        const failures = 'Complete failure index: '+JSON.stringify(index)+'\n'+
          failed.map(row => readFileSync(row.log,'utf8').slice(-1800)).join('\n').slice(0,6000);
        if (accepted) {
          const session = process.env.QWEN_WORKFLOW_SESSION;
          if (session) writeFileSync(join(session,'completion-stop.json'),JSON.stringify({
            reason:'Automatic frozen tests and fresh atomic gate passed after source edit',
            finished_epoch:Date.now()/1000,shadow_snapshot:gate.shadow_snapshot,
          },null,2));
          ctx.abort();
        }
        return {content:[...event.content,{type:'text',text:'Shadow refreshed: '+summary.snapshot+
          '\nAutomatic frozen tests and gate:\n'+tests.stdout+'\n'+checked.stdout+'\n'+failures}],
          details:{...(event.details||{}),shadow:summary,automaticTestsPassed:tests.code===0,
            gatePassed:gate.passed,acceptedCompletion:accepted}};
      }
      const recovery=architectureEdit ? '' : await failedEditEvidence(pi,event,ctx,python,cli,scopeArgs);
      return { content: [...event.content, { type: 'text', text: 'Shadow refreshed: ' + summary.snapshot + recovery }],
        details: { ...(event.details || {}), shadow: summary } };
    } catch (error) {
      return { isError: true, content: [...event.content,
        { type: 'text', text: 'Shadow refresh failed; completion is blocked: ' + error.message }] };
    } finally {
      if (event.input?.path || architectureEdit) {
        const target = architectureEdit ? resolve(process.env.QWEN_WORKFLOW_PROJECT, 'architecture.md') : resolve(ctx.cwd, event.input.path);
        if (mutations.get(target) === event.toolCallId) mutations.delete(target);
      }
    }
  });
  pi.on('agent_before_settle', async (_event, ctx) => { if (active(ctx.model)) await refresh(ctx); });
}
