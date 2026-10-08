/** Explicit local-Qwen-only adapter; loading this file does not alter Codex. */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import {randomUUID} from 'node:crypto';
import { Type } from '@earendil-works/pi-ai';
import { applies, active, installPromptHooks, installToolHooks, installRefreshHooks } from './pi-hooks.mjs';
import { installCompactionHooks } from './pi-compaction.mjs';
import { installFixedCompactionHooks } from './pi-compaction-fixed.mjs';
import { installTimingHooks } from './pi-timing.mjs';
import {registerResearch} from './pi-research.mjs';
import {registerDomainSkills} from './pi-domain-skills.mjs';
import {registerSkills} from './pi-skills.mjs';
import {registerPhases} from './pi-phases.mjs';
import {registerRemember} from './pi-remember.mjs';
import {installInitialPrompt} from './pi-intake.mjs';
import {registerRoleSelection} from './pi-role-selection.mjs';
import {registerReview} from './pi-review.mjs';
import {registerThinkingCap} from './pi-thinking-cap.mjs';
import {registerChat} from './pi-chat.mjs';
import {registerMemory} from './pi-memory.mjs';
import {registerServer} from './pi-server.mjs';
import {registerPlanChildren} from './pi-plan-children.mjs';
import {repairParameters} from './pi-plan-draft.mjs';
import {coverageParameters} from './pi-coverage-plan.mjs';
import {recoveryParameters} from './pi-replan-patch.mjs';
import {installExecutionProgressHooks} from './pi-execution-progress.mjs';
import {rememberSource} from './pi-source-memory.mjs';
import {recoverySourceEnabled} from './pi-hooks.mjs';
import {sectionLookup,navigationReply} from './pi-map-navigation.mjs';
import {installPlanningFinish} from './pi-planning-finish.mjs';
import {registerRecoveryReport} from './pi-recovery-report.mjs';
export { applies } from './pi-hooks.mjs';

const home = dirname(fileURLToPath(import.meta.url));
const python = join(home, '.venv/bin/python');
const cli = join(process.env.QWEN_WORKFLOW_RUNTIME || home, 'workflow.py');

function scopeArgs(root) {
  const prefixes = JSON.parse(process.env.QWEN_WORKFLOW_PREFIXES || '["."]');
  return ['--root', root, ...prefixes.flatMap(prefix => ['--prefix', prefix])];
}

export function commandFor(action, paths, query, state, offset = 0, sectionOffset = 0, sha256 = '') {
  if (action === 'sync-check' && process.env.QWEN_WORKFLOW_SHADOW) return ['architecture-status', '--shadow', process.env.QWEN_WORKFLOW_SHADOW, ...(process.env.QWEN_WORKFLOW_STATE ? ['--state', process.env.QWEN_WORKFLOW_STATE] : [])];
  if (action === 'catalog') return ['catalog', '--offset', String(offset)];
  if (action === 'architecture') return ['architecture', '--offset', String(offset), '--section-offset', String(sectionOffset), ...(paths?.length ? ['--paths', ...paths] : [])];
  if (action === 'architecture-section' && query && sha256) return ['architecture-section', query, '--sha256', sha256, '--offset', String(offset)];
  if (sectionLookup(action,query,sha256)) return ['architecture-search', query, '--offset', '0'];
  if (action === 'architecture-section') throw new Error('Supply a section ID and its source_sha256, or a filename/keyword to look up matching IDs. No section was read.');
  if (action === 'architecture-search' && query) return ['architecture-search', query, '--offset', String(offset)];
  if (action === 'locate') {
    if (!query?.trim()) throw new Error('project_map locate requires a nonempty query (symbol or filename keyword). To read prototypes for known files, use action=inspect with paths and no query.');
    return ['locate', query, ...(paths?.length ? ['--paths', ...paths] : [])];
  }
  if (action === 'inspect' && paths?.length) return ['context', ...paths, '--max-bytes', '24000', ...(query ? ['--symbol', query] : [])];
  if (action === 'gate') {
    const frozen=process.env.QWEN_WORKFLOW_STATE;
    if(frozen&&state&&resolve(state)!==resolve(frozen))throw new Error('Gate state must be this worker\'s frozen task; omit state to use it.');
    if(frozen||state)return ['check','--state',frozen||state];
    throw new Error('No frozen task is active; gate requires a bound task state.');
  }
  throw new Error('Supply paths for inspect, query for locate, or state for gate');
}

export default function (pi) {
  const mutations = new Map();
  installPromptHooks(pi, home);
  installToolHooks(pi, mutations);
  installRefreshHooks(pi, python, cli, scopeArgs, mutations);
  installExecutionProgressHooks(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  (process.env.QWEN_WORKFLOW_COMPACTION_FIX === '1' ? installFixedCompactionHooks : installCompactionHooks)(pi, python, cli);
  installTimingHooks(pi);
  installPlanningFinish(pi);
  registerRecoveryReport(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  registerMap(pi);
  pi.registerCommand('rebuild', {description:'Rebuild this session architecture/shadow/map after an explicit user request',
    handler:async (_args,ctx)=>{
      if (!active(ctx.model)) throw new Error('Rebuild belongs only to mypi');
      const session=process.env.QWEN_WORKFLOW_SESSION;
      const request=join(session,'architecture-rebuild-request.json');
      const runner=join(process.env.QWEN_WORKFLOW_RUNTIME || home,'skill_runner.py');
      const role=process.env.QWEN_WORKFLOW_ROLE;
      const argv=[runner,'--session',session,'--role',role,'--request',request];
      writeFileSync(request,JSON.stringify({action:'prepare',name:'architecture-sync-check'}));
      const prepared=await pi.exec(python,argv,{timeout:10000});
      if(prepared.code)throw new Error(prepared.stdout+prepared.stderr);
      writeFileSync(request,JSON.stringify({action:'run',name:'architecture-sync-check',inputs:{action:'rebuild'}}));
      const result=await pi.exec(python,argv,{timeout:50000});
      ctx.ui.notify(result.code ? 'Rebuild failed: '+result.stdout+result.stderr : 'Architecture, shadow and map rebuilt; current evidence verified.',result.code?'error':'info');
    }});
  registerSource(pi);
  registerTests(pi);
  registerPlan(pi);
  registerPlanChildren(pi,python,cli,scopeArgs,active);
  registerResearch(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  registerDomainSkills(pi,active);
  registerSkills(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  registerPhases(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  registerRemember(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  installInitialPrompt(pi,python);
  registerRoleSelection(pi,python);
  registerReview(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  registerThinkingCap(pi,python);
  registerChat(pi);
  registerMemory(pi,python,process.env.QWEN_WORKFLOW_RUNTIME || home);
  registerServer(pi,python);
}

function registerMap(pi) {
  /** Expose only bounded current interfaces and completion evidence. */
  pi.registerTool({
    name: 'project_map',
    label: 'Project interfaces',
    description: 'Brief architecture decisions and shadow links, symbol search, bounded prototypes, or atomic task gate. inspect requires paths and returns their prototypes; query is optional. locate requires a nonempty query (symbol or filename keyword), with optional paths to narrow the search; do not use locate with paths alone. Planning size is measured at launch. Above 32768 shadow+architecture tokens, architecture is the only project-wide map: read its pages first, then inspect 1-5 relevant module paths already shown there (8192 text tokens maximum). locate must include those explicit paths; catalog is blocked. Architecture returns a compact section index and module page; offset pages modules, section_offset pages headings. architecture-search performs literal keyword/function/class map search (query, offset). architecture-section reads one section ID in query, current source sha256, and character offset. Reload relevant sections per todo, rather than full architecture prose. Read implementations before editing.',
    parameters: Type.Object({
      action: Type.Union(['architecture', 'architecture-section', 'architecture-search', 'sync-check', 'catalog', 'locate', 'inspect', 'gate'].map(x => Type.Literal(x))),
      paths: Type.Optional(Type.Array(Type.String())),
      query: Type.Optional(Type.String({description:'Required for locate (symbol/filename keyword), architecture-search (keyword), and architecture-section (section ID). A section query without sha256 performs a bounded filename/keyword index lookup and returns next_calls, not section text. Optional symbol filter for inspect.'})),
      state: Type.Optional(Type.String({description:'Gate defaults to this worker\'s frozen task state. Omit it during atomic execution; an explicit path must match the bound state.'})),
      section_offset: Type.Optional(Type.Integer({ minimum: 0 })),
      sha256: Type.Optional(Type.String()),
      offset: Type.Optional(Type.Integer({ minimum: 0 })),
    }),
    async execute(_id, params, signal, _update, ctx) {
      if (!active(ctx.model)) throw new Error('This tool belongs only to the explicit workflow');
      const root = process.env.QWEN_WORKFLOW_PROJECT || ctx.cwd;
      const args = [...scopeArgs(root), ...commandFor(params.action, params.paths, params.query, params.state, params.offset, params.section_offset, params.sha256)];
      const result = await pi.exec(python, [cli, ...args], { signal, timeout: 30000 });
      let gate;
      if(params.action==='gate') {
        try{gate=JSON.parse(result.stdout);}catch{}
      }
      const failedGate=params.action==='gate'&&result.code===1&&gate?.passed===false&&Array.isArray(gate.violations);
      if (result.code&&!failedGate) throw new Error((result.stdout + result.stderr).slice(0, 8000));
      const text = navigationReply(params,result.stdout);
      return {
        content: [{ type: 'text', text: text.length <= 16000 ? text :
          text.slice(0, 16000) + '\n[Navigation truncated; use selected architecture paths/pages and narrower prototype queries.]' }],
        details: { action: params.action, truncated: text.length > 16000,
          ...(sectionLookup(params.action,params.query,params.sha256)?{resolvedAction:'architecture-search',sectionRead:false}:{}),
          ...(gate?{gatePassed:gate.passed===true}: {}) },
      };
    },
  });
}

function registerSource(pi) {
  /** Retrieve one symbol or bounded references for the local executor. */
  pi.registerTool({
    name: 'source_query', label: 'Targeted source',
    description: 'Read qualified functions/classes or variable/constant definitions including initializers with symbol (short names must match uniquely within each file). Symbol accepts 1-5 explicit file paths and returns all matching names with path labels under one combined 12 KB budget; filenames and names are never paired by position. For paging, select one file and one symbol. variables returns declaration metadata only and defaults to all. Also supports literal rg matches or one bounded source page. symbol/search require query. file reads one exact project file OR the exact test-log path reported by this current task, with optional line offset and no query. Test logs are read-only evidence; other session files are inaccessible. fixture reads an exact absolute pinned test file from frozen tests argv, with no query; project source passed as fixture is served as a bounded file page. Never pass a directory or test index. Symbol batches accept 1-8 whitespace-separated names. Line prefixes are navigation labels, not edit text. Read supplied spans first; use next_offset only when more=true.',
    parameters: Type.Object({
      action: Type.Union(['symbol', 'variables', 'search', 'file', 'fixture'].map(x => Type.Literal(x))),
      paths: Type.Array(Type.String(), { minItems: 1, maxItems: 5 }),
      query: Type.Optional(Type.String()), offset: Type.Optional(Type.Integer({ minimum: 0 })),
    }),
    async execute(_id, params, signal, _update, ctx) {
      if (!active(ctx.model) || (!['code','inspect'].includes(process.env.QWEN_WORKFLOW_ROLE) && !recoverySourceEnabled())) throw new Error('Coding, read-only inspection or bound failure recovery only');
      if(['symbol','search'].includes(params.action)&&!params.query?.trim())throw new Error('source_query '+params.action+' requires a nonempty query. To read a project file page, use action=file and paths=[exact filename], with no query.');
      if(!['search','symbol'].includes(params.action)&&params.paths.length!==1)throw new Error('Select exactly one file for '+params.action+'; symbol/search accept multiple paths.');
      const names = params.action === 'symbol' ? params.query.trim().split(/\s+/) : [];
      if(params.action==='symbol'&&params.paths.length>1&&params.offset)throw new Error('Page one named symbol in one file when using offset.');
      const subcommand = params.action === 'symbol' ? (params.paths.length>1 ?
        ['read-symbols-across',...params.paths,'--names',...names] : names.length > 1 ?
        ['read-symbols', params.paths[0], ...names] :
        ['read-symbol', params.paths[0], names[0], '--offset', String(params.offset || 0)]) :
        ['file','fixture'].includes(params.action) ? ['read-file', params.paths[0], '--offset', String(params.offset || 0),...(params.action==='fixture'?['--fixture-request']:[])] :
        params.action === 'variables' ? ['variables', params.paths[0], '--query', params.query === 'all' ? '' : (params.query||'')] :
        ['search', ...params.paths, '--pattern', params.query];
      const result = await pi.exec(python, [cli, ...scopeArgs(process.env.QWEN_WORKFLOW_PROJECT || ctx.cwd), ...subcommand], { signal, timeout: 30000 });
      if (result.code) throw new Error((result.stdout + result.stderr).slice(0, 8000));
      if(process.env.QWEN_WORKFLOW_ROLE==='code')rememberSource(process.env.QWEN_WORKFLOW_SESSION,
        process.env.QWEN_WORKFLOW_PROJECT || ctx.cwd,result.stdout);
      return { content: [{ type: 'text', text: result.stdout.slice(0, 16000) }], details: { action: params.action } };
    },
  });
}

function registerTests(pi) {
  /** One call performs the reviewed native finalization skill and returns compact evidence. */
  pi.registerTool({
    name:'workflow_test',label:'Finalize task and verify',
    description:'Run frozen tests and the completion gate. If an architecture note is required, pass one brief architecture_note and optional architecture_title: Python handles scoped insertion, hashes, shadow/map refresh and verification in this same call. Do not rewrite passing source to fix a missing note.',
    parameters:Type.Object({architecture_note:Type.Optional(Type.String({minLength:1,maxLength:1200})),
      architecture_title:Type.Optional(Type.String({minLength:1,maxLength:120}))}),
    async execute(_id,params,signal,_update,ctx) {
      const state=process.env.QWEN_WORKFLOW_STATE;
      if(!active(ctx.model)||process.env.QWEN_WORKFLOW_ROLE!=='code'||!state)throw new Error('Coding phase needs a task contract');
      const request=join(process.env.QWEN_WORKFLOW_SESSION,'finalization-input-'+randomUUID()+'.json');
      writeFileSync(request,JSON.stringify(params));
      const result=await pi.exec(python,[cli,'finalize','--state',state,'--input',request],{signal,timeout:2705000});
      let data;try{data=JSON.parse(result.stdout);}catch{throw new Error((result.stdout+result.stderr).slice(0,2000));}
      return {content:[{type:'text',text:result.stdout}],
        details:{testsPassed:data.tests_passed===true,gatePassed:data.passed===true}};
    }
  });
}

export function failureFeedback(failures) {
  const entries = failures.map(row => {
    const text = readFileSync(row.log, 'utf8');
    const names = text.split('\n').filter(line => /^(?:not ok|[✖×]|\s*failureType:|\s*error:)/.test(line)).map(line => line.slice(0,300));
    return {log:row.log, exit_code:row.exit_code, failing_tests:names, excerpt:text.slice(-1800)};
  });
  const index = entries.map(({excerpt,...entry}) => entry);
  return 'Complete failure index (retrieve fixtures for details):\n' + JSON.stringify(index) +
    '\nBounded diagnostic excerpts:\n' + JSON.stringify(entries.map(({log,excerpt})=>({log,excerpt}))).slice(0,6000);
}

function registerPlan(pi) {
  /** Persist structured todos outside the project; planning cannot execute them. */
  const draft=process.env.QWEN_WORKFLOW_PLAN_DRAFT;
  const recovery=process.env.QWEN_WORKFLOW_REPLAN_EVIDENCE;
  const target=draft && process.env.QWEN_WORKFLOW_PLAN_COVERAGE!=='1' ? JSON.parse(readFileSync(draft,'utf8')).refine_task : undefined;
  const refinement=target ? 'Refine only '+target+': pass changed fields DIRECTLY (steps, context_overlay, add_tests, add_coverage, etc). Python supplies the target ID. Do not send task_updates, id, tasks or replace_with. For a split, stage each full child with plan_child_store and submit its ordered child_refs here. Use unchanged:true only if no changes are needed. Every save starts from the pinned draft; rejected saves do not accumulate edits.' : '';
  pi.registerTool({
    name: 'plan_store', label: 'Save architecture and todos',
    description: recovery ? 'Repair only the failed todo: provide recovery_decision(action=repair), failure_analysis, strategy_review and changed steps beginning with the exact first_check; context_overlay is optional. Python preserves all unchanged tasks, exact acceptance, tests and dependency order. Do not send tasks, task_updates, goal, IDs or a whole replacement plan. Source edits belong to the executor.' : process.env.QWEN_WORKFLOW_PLAN_COVERAGE === '1' ? 'Attach coverage_plan to the unchanged pinned draft. Map every acceptance case and request requirement to observable checks, and assign missing cases to tasks. Does not implement tests.' : target ? refinement : draft ? 'Repair the pinned unaccepted proposal with sparse task_updates and exact architecture_replacements. Python preserves unchanged tasks, criteria and tests, then validates and saves the complete V3 plan. Never resend the entire draft.'+refinement : 'Save one detailed plan with ordered atomic todos. Does not edit source or execute tasks.',
    parameters: recovery ? recoveryParameters() : process.env.QWEN_WORKFLOW_PLAN_COVERAGE === '1' ? coverageParameters() : draft ? repairParameters(target) : Type.Object({ plan_version: Type.Optional(Type.Literal(3)),
      goal: Type.String(), architecture: Type.String(),
      failure_analysis: Type.Optional(Type.String({minLength:40,description:'For evidence-bound recovery: observed failure, cause/hypothesis, corrective approach and validation.'})),
      tasks: Type.Union([Type.Array(Type.Object({ id: Type.String(), goal: Type.String(),
        steps: Type.Optional(Type.Array(Type.String(), {minItems:2,maxItems:6})),
        assumptions: Type.Optional(Type.Array(Type.String())),
        test_strategy: Type.Optional(Type.String()),
        estimated_changed_lines: Type.Integer({minimum:1,maximum:300}),
        execution: Type.Optional(Type.Object({timeout_seconds:Type.Integer({minimum:30,maximum:2700}),
          test_timeout_seconds:Type.Integer({minimum:1,maximum:300}),on_failure:Type.Literal('replan')})),
        acceptance: Type.Array(Type.Object({ id: Type.String(), given: Type.String(), when: Type.String(), then: Type.String() })),
        files: Type.Array(Type.String()),
        tests: Type.Array(Type.Array(Type.String())), inspect: Type.Optional(Type.Array(Type.String())),
        coverage: Type.Array(Type.Object({ criterion: Type.String({ description: 'Exact acceptance id, e.g. T1-A; never a prose description.' }), test: Type.Integer({ minimum: 0, description: 'Zero-based index into THIS task tests array of argv commands. When there is one command, ALWAYS use literal 0, regardless of how many fixture files it names.' }) })),
        context: Type.Object({ interfaces: Type.Array(Type.String()),
          architecture_sections: Type.Optional(Type.Array(Type.Object({id: Type.String(), sha256: Type.String()}), {maxItems:5})),
          architecture_update_required: Type.Optional(Type.Boolean()),
          symbols: Type.Array(Type.Object({ path: Type.String(), name: Type.String() })),
          reference_files: Type.Array(Type.String()),
          preset: Type.Optional(Type.Union(['small','standard','large'].map(x=>Type.Literal(x)))),
          window_tokens: Type.Optional(Type.Union([32768,65536,98304,131072].map(x=>Type.Literal(x)))),
          thinking: Type.Optional(Type.Union(['on','off'].map(x=>Type.Literal(x)))),
          reasoning_effort: Type.Optional(Type.Union(['low','medium','xhigh'].map(x=>Type.Literal(x)))),
          reasoning_budget_tokens: Type.Optional(Type.Integer({minimum:0,maximum:30720})),
          research_briefs: Type.Optional(Type.Array(Type.String(),{maxItems:2})),
          knowledge_topics: Type.Optional(Type.Array(Type.String(),{maxItems:4})),
          selected_symbols_only: Type.Optional(Type.Boolean()),
          fixture_test_patterns: Type.Optional(Type.Array(Type.String(),{maxItems:8})),
          estimate: Type.Optional(Type.Object(Object.fromEntries(['framework','shadow','source','tests','history']
            .map(key=>[key,Type.Integer({minimum:key==='framework'?6144:0})])))),
          margin_tokens: Type.Optional(Type.Integer({minimum:1024})),
          max_input_tokens: Type.Integer({minimum:512,maximum:57344}),
          max_output_tokens: Type.Integer({minimum:512,maximum:32768}) }),
        depends_on: Type.Optional(Type.Array(Type.String())) })),
        Type.String({maxLength:1048576,description:'Compatibility for a literal JSON array serialized by a tool adapter. Prefer an array of task objects. Python parses strictly and validates every contract.'})]) }),
    async execute(_id, params, signal, _update, ctx) {
      if (!active(ctx.model) || !['architect','reviewer'].includes(process.env.QWEN_WORKFLOW_ROLE)) throw new Error('Planning or final review only');
      if (params.plan_version !== undefined && params.plan_version !== 3) throw new Error('New executable plans require plan_version 3 with context estimates and bounded execution.');
      const output = process.env.QWEN_WORKFLOW_PLAN;
      if (!output) throw new Error('Plan destination missing');
      const input = output + '.draft.json';
      writeFileSync(input, JSON.stringify((draft || recovery) ? params : {...params,plan_version:params.plan_version || 3}));
      const result = await pi.exec(python, [cli, ...scopeArgs(process.env.QWEN_WORKFLOW_PROJECT),
        'save-plan', '--input', input, '--output', output], { signal, timeout: 30000 });
      if (result.code) throw new Error(result.stdout + result.stderr);
      return { content: [{ type: 'text', text: result.stdout }], details: { plan: output } };
    },
  });
}
