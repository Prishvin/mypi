/** Explicit local-Qwen-only adapter; loading this file does not alter Codex. */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
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
import {repairParameters} from './pi-plan-draft.mjs';
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
  if (action === 'architecture-search' && query) return ['architecture-search', query, '--offset', String(offset)];
  if (action === 'locate' && query) return ['locate', query, ...(paths?.length ? ['--paths', ...paths] : [])];
  if (action === 'inspect' && paths?.length) return ['context', ...paths, '--max-bytes', '24000', ...(query ? ['--symbol', query] : [])];
  if (action === 'gate' && state) return ['check', '--state', state];
  throw new Error('Supply paths for inspect, query for locate, or state for gate');
}

export default function (pi) {
  const mutations = new Map();
  installPromptHooks(pi, home);
  installToolHooks(pi, mutations);
  installRefreshHooks(pi, python, cli, scopeArgs, mutations);
  (process.env.QWEN_WORKFLOW_COMPACTION_FIX === '1' ? installFixedCompactionHooks : installCompactionHooks)(pi, python, cli);
  installTimingHooks(pi);
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
    description: 'Brief architecture decisions and shadow links, symbol search, bounded prototypes, or atomic task gate. Planning size is measured at launch. Above 32768 shadow+architecture tokens, architecture is the only project-wide map: read its pages first, then inspect 1-5 relevant module paths already shown there (8192 text tokens maximum). locate must include those explicit paths; catalog is blocked. Architecture returns a compact section index and module page; offset pages modules, section_offset pages headings. architecture-search performs literal keyword/function/class map search (query, offset). architecture-section reads one section ID in query, current source sha256, and character offset. Reload relevant sections per todo, rather than full architecture prose. Read implementations before editing.',
    parameters: Type.Object({
      action: Type.Union(['architecture', 'architecture-section', 'architecture-search', 'sync-check', 'catalog', 'locate', 'inspect', 'gate'].map(x => Type.Literal(x))),
      paths: Type.Optional(Type.Array(Type.String())),
      query: Type.Optional(Type.String()),
      state: Type.Optional(Type.String()),
      section_offset: Type.Optional(Type.Integer({ minimum: 0 })),
      sha256: Type.Optional(Type.String()),
      offset: Type.Optional(Type.Integer({ minimum: 0 })),
    }),
    async execute(_id, params, signal, _update, ctx) {
      if (!active(ctx.model)) throw new Error('This tool belongs only to the explicit workflow');
      const root = process.env.QWEN_WORKFLOW_PROJECT || ctx.cwd;
      const args = [...scopeArgs(root), ...commandFor(params.action, params.paths, params.query, params.state, params.offset, params.section_offset, params.sha256)];
      const result = await pi.exec(python, [cli, ...args], { signal, timeout: 30000 });
      if (result.code) throw new Error((result.stdout + result.stderr).slice(0, 8000));
      const text = result.stdout;
      return {
        content: [{ type: 'text', text: text.length <= 16000 ? text :
          text.slice(0, 16000) + '\n[Navigation truncated; use selected architecture paths/pages and narrower prototype queries.]' }],
        details: { action: params.action, truncated: text.length > 16000 },
      };
    },
  });
}

function registerSource(pi) {
  /** Retrieve one symbol or bounded references for the local executor. */
  pi.registerTool({
    name: 'source_query', label: 'Targeted source',
    description: 'Read exact qualified symbols (1-8 whitespace-separated names from one file), variable declarations (whitespace-separated names or all), bounded literal rg, or a pinned acceptance fixture page. For fixture: paths[0] is the exact absolute fixture file from the frozen tests argv; query is empty. Never supply the project directory, a test index, or just the external filename. Valid symbols survive missing names in a batch. Source line prefixes are navigation labels, not edit text. Read supplied spans before fetching; use next_offset only when more is true. Coding or read-only inspection phase only.',
    parameters: Type.Object({
      action: Type.Union(['symbol', 'variables', 'search', 'fixture'].map(x => Type.Literal(x))),
      paths: Type.Array(Type.String(), { minItems: 1, maxItems: 5 }),
      query: Type.String(), offset: Type.Optional(Type.Integer({ minimum: 0 })),
    }),
    async execute(_id, params, signal, _update, ctx) {
      if (!active(ctx.model) || !['code','inspect'].includes(process.env.QWEN_WORKFLOW_ROLE)) throw new Error('Coding or read-only inspection phase only');
      const subcommand = params.action === 'symbol' ? (params.query.includes(' ') ?
        ['read-symbols', params.paths[0], ...params.query.split(/\s+/).filter(Boolean)] :
        ['read-symbol', params.paths[0], params.query, '--offset', String(params.offset || 0)]) :
        params.action === 'fixture' ? ['read-fixture', params.paths[0], '--offset', String(params.offset || 0)] :
        params.action === 'variables' ? ['variables', params.paths[0], '--query', params.query === 'all' ? '' : params.query] :
        ['search', ...params.paths, '--pattern', params.query];
      const result = await pi.exec(python, [cli, ...scopeArgs(process.env.QWEN_WORKFLOW_PROJECT || ctx.cwd), ...subcommand], { signal, timeout: 30000 });
      if (result.code) throw new Error((result.stdout + result.stderr).slice(0, 8000));
      return { content: [{ type: 'text', text: result.stdout.slice(0, 16000) }], details: { action: params.action } };
    },
  });
}

function registerTests(pi) {
  /** Execute only frozen test commands and return failure evidence. */
  pi.registerTool({
    name: 'workflow_test', label: 'Declared unit tests',
    description: 'Run the frozen task test commands and save validation evidence. No arbitrary shell command.',
    parameters: Type.Object({}),
    async execute(_id, _params, signal, _update, ctx) {
      const state = process.env.QWEN_WORKFLOW_STATE;
      if (!active(ctx.model) || process.env.QWEN_WORKFLOW_ROLE !== 'code' || !state) throw new Error('Coding phase needs a task contract');
      const result = await pi.exec(python, [cli, 'test', '--state', state], { signal, timeout: 310000 });
      const gate = await pi.exec(python, [cli, 'check', '--state', state], { signal, timeout: 30000 });
      const failures = JSON.parse(result.stdout).results.filter(row => row.exit_code);
      const tails = failureFeedback(failures);
      return { content: [{ type: 'text', text: tails + '\n' + (result.stdout + gate.stdout).slice(0, 6000) }],
        details: { testsPassed: result.code === 0, gatePassed: gate.code === 0 } };
    },
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
  pi.registerTool({
    name: 'plan_store', label: 'Save architecture and todos',
    description: process.env.QWEN_WORKFLOW_PLAN_DRAFT ? 'Repair the pinned unaccepted proposal with sparse task_updates and exact architecture_replacements. Python preserves unchanged tasks, criteria and tests, then validates and saves the complete V3 plan. Never resend the entire draft.' : 'Save one detailed plan with ordered atomic todos. Does not edit source or execute tasks.',
    parameters: process.env.QWEN_WORKFLOW_PLAN_DRAFT ? repairParameters() : Type.Object({ plan_version: Type.Optional(Type.Literal(3)),
      goal: Type.String(), architecture: Type.String(),
      tasks: Type.Array(Type.Object({ id: Type.String(), goal: Type.String(),
        steps: Type.Optional(Type.Array(Type.String(), {minItems:2,maxItems:6})),
        assumptions: Type.Optional(Type.Array(Type.String())),
        test_strategy: Type.Optional(Type.String()),
        estimated_changed_lines: Type.Integer({minimum:1,maximum:300}),
        execution: Type.Optional(Type.Object({timeout_seconds:Type.Integer({minimum:30,maximum:1200}),
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
            .map(key=>[key,Type.Integer({minimum:0})])))),
          margin_tokens: Type.Optional(Type.Integer({minimum:1024})),
          max_input_tokens: Type.Integer({minimum:512,maximum:57344}),
          max_output_tokens: Type.Integer({minimum:512,maximum:32768}) }),
        depends_on: Type.Optional(Type.Array(Type.String())) })) }),
    async execute(_id, params, signal, _update, ctx) {
      if (!active(ctx.model) || !['architect','reviewer'].includes(process.env.QWEN_WORKFLOW_ROLE)) throw new Error('Planning or final review only');
      if (params.plan_version !== undefined && params.plan_version !== 3) throw new Error('New executable plans require plan_version 3 with context estimates and bounded execution.');
      const output = process.env.QWEN_WORKFLOW_PLAN;
      if (!output) throw new Error('Plan destination missing');
      const input = output + '.draft.json';
      writeFileSync(input, JSON.stringify(process.env.QWEN_WORKFLOW_PLAN_DRAFT ? params : {...params,plan_version:params.plan_version || 3}));
      const result = await pi.exec(python, [cli, ...scopeArgs(process.env.QWEN_WORKFLOW_PROJECT),
        'save-plan', '--input', input, '--output', output], { signal, timeout: 30000 });
      if (result.code) throw new Error(result.stdout + result.stderr);
      return { content: [{ type: 'text', text: result.stdout }], details: { plan: output } };
    },
  });
}
