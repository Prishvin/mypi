"""Launch an isolated Pi workflow with an explicitly selected local Qwen model."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import platform_paths
import urllib.request
import uuid
import time
from project_map import scan, write_map
import tasks
import shadow
import plans
import planner
import progress
import runtime
import prefetch
import profiles
import task_prompts
import workflow_skills
import server_config

BASE = Path(__file__).resolve().parent
PI = platform_paths.pi(BASE)
MODELS = {name: ('mtplx-' + name, 8000) for name in ('quality', 'speed', 'gemma')}
MODELS.update({'27b': ('qwen27b-q8', 8081), 'flash': ('flash-next-local', 8080)})
CONTEXT_LIMITS = {name: 98304 for name in MODELS}
CONTEXT_LIMITS['flash'] = 131072


def validate_model_context(model: str, context: int) -> None:
    """Enforce the user's per-model ceiling before contacting a server."""
    if context > CONTEXT_LIMITS[model]:
        raise ValueError(f'{model} workflow context exceeds its {CONTEXT_LIMITS[model]} token ceiling')


def configure(folder: Path, model: str, context: int) -> None:
    """Write private Pi settings; do not change global settings or Codex instructions."""
    alias, port = MODELS[model]
    connection = server_config.load() if model == 'quality' else None
    if connection:
        alias = connection['model']
    folder.mkdir(parents=True, exist_ok=True)
    descriptor = {'id': alias, 'name': alias, 'reasoning': True, 'input': ['text'],
                  'contextWindow': context, 'maxTokens': 8192 if context <= 32768 else 32768,
                  'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0},
                  'compat': {'supportsStore': False, 'supportsDeveloperRole': False,
                             'supportsReasoningEffort': False,
                             'requiresReasoningContentOnAssistantMessages': model != 'gemma'}}
    config = {'providers': {'local-qwen-workflow': {
        'baseUrl': connection['url'] + '/v1' if connection else f'http://127.0.0.1:{port}/v1', 'api': 'openai-completions',
        'apiKey': 'MYPI_SERVER_TOKEN' if os.environ.get('MYPI_SERVER_TOKEN') else 'local', 'models': [descriptor]}}}
    (folder / 'models.json').write_text(json.dumps(config, indent=2))
    settings = {'packages': [], 'extensions': [], 'skills': [], 'promptTemplates': [],
                'quietStartup': True, 'defaultProjectTrust': 'never',
                'compaction': {'enabled': True, 'reserveTokens': descriptor['maxTokens'],
                               'keepRecentTokens': min(12000, context // 4)}}
    (folder / 'settings.json').write_text(json.dumps(settings, indent=2))


def check_server(model: str, context: int, connection=None) -> None:
    """Require a healthy chosen model and confirm its real server context setting."""
    validate_model_context(model, context)
    alias, port = MODELS[model]
    base = f'http://127.0.0.1:{port}'
    if model == 'quality':
        connection = connection or server_config.load(); base = connection['url']; alias = connection['model']
    with urllib.request.urlopen(urllib.request.Request(base + '/v1/models', headers=server_config.headers()), timeout=5) as response:
        models = json.load(response)
    if alias not in {row['id'] for row in models['data']}:
        raise ValueError('The selected endpoint is serving a different model')
    with urllib.request.urlopen(urllib.request.Request(base + ('/props' if model in ('27b', 'flash') else '/health'), headers=server_config.headers()), timeout=5) as response:
        properties = json.load(response)
    window = properties.get('execution_window')
    actual = properties.get('default_generation_settings', {}).get('n_ctx') if model in ('27b', 'flash') else (
        window.get('tokens') if isinstance(window,dict) else window or properties.get('context_window'))
    if actual is None or actual < context:
        raise ValueError(f'Server context {actual} does not verify requested context {context}')
    if model in ('quality','speed'):
        expected=os.environ.get('QWEN_WORKFLOW_HISTORY_POLICY','auto')
        if properties.get('preserve_thinking') != expected:
            raise ValueError(f'Server thinking history is {properties.get("preserve_thinking")!r}; this workflow requires {expected!r}. Restart its guard with --preserve-thinking {expected}.')


def prepare(args) -> dict:
    """Create a shadow and a fresh, provider-specific session outside the project."""
    profile = profiles.apply_identity(args)
    task = selected_task(args) if args.role == 'code' else {}
    if getattr(args,'task_instructions_file',None):
        instruction=json.loads(args.task_instructions_file.read_text())
        if args.role!='code' or instruction.get('todo')!=task.get('id'):
            raise ValueError('User instructions do not match the selected coding task')
        text=instruction.get('prompt')
        if not isinstance(text,str) or not text.strip() or len(text.encode())>24000:
            raise ValueError('User task instructions must contain 1–24000 bytes')
        task={**task,'user_instructions':text}
    effective = profiles.resolve(args, task, profile)
    args.context = effective['context']
    args.reasoning = effective['reasoning']
    args.thinking = effective['thinking']
    args.reasoning_budget = effective['reasoning_budget']
    args.stop_after_pass = effective['stop_after_pass']
    reasoning_budget = getattr(args, 'reasoning_budget', None)
    if reasoning_budget is not None and not 0 <= reasoning_budget <= 32768:
        raise ValueError('Reasoning budget must be 0-32768 tokens')
    root = args.project.resolve()
    executor = getattr(args, 'executor', 'local')
    cloud = args.planner == 'chatgpt' if args.role in ('architect', 'research', 'intake','reviewer','memory') else executor == 'chatgpt'
    if not cloud:validate_model_context(args.model,args.context)
    if cloud and not args.planner_model:
        raise ValueError('ChatGPT planning or execution requires --planner-model')
    if args.briefs:
        os.environ['QWEN_WORKFLOW_BRIEFS'] = str(args.briefs.resolve())
    session = BASE / 'sessions' / uuid.uuid4().hex[:12]
    session.mkdir(parents=True)
    pinned = runtime.capture(BASE, session)
    skill_text = workflow_skills.instructions(pinned, args.role)
    (session / 'active-skills.txt').write_text(skill_text)
    shadow_path = session / 'shadow'
    prefixes = args.prefix or ['.']
    summary = shadow.refresh(root, prefixes, shadow_path)
    draft_path = None
    evidence_path=None
    if getattr(args,'replan_evidence',None):
        evidence=json.loads(args.replan_evidence.read_text())
        if args.role!='architect' or evidence['project']!=str(root) or evidence['current_snapshot']!=summary['snapshot']:
            raise ValueError('Replan evidence does not match this architect and source snapshot')
        from plan_draft import digest
        from strategy_review import POLICY
        evidence['strategy_review_policy'] = dict(POLICY)
        from recovery_protocol import POLICY as RECOVERY_POLICY
        evidence['failure_recovery_policy'] = dict(RECOVERY_POLICY)
        evidence['recovery_plan_sha256']=digest(json.loads(Path(evidence['plan']).read_text()))
        evidence_path=str(session/'replan-evidence.json');Path(evidence_path).write_text(json.dumps(evidence))
    if getattr(args, 'plan_draft', None):
        if args.role != 'architect' or getattr(args, 'interactive', False):
            raise ValueError('Unaccepted draft repair needs a batch architect session')
        from plan_draft import bind
        draft_path = bind(root, args.plan_draft, session/'plan-draft.json', summary['snapshot'],getattr(args,'refine_task',None),getattr(args,'plan_coverage',False))
    elif getattr(args,'refine_task',None) or getattr(args,'plan_coverage',False):
        raise ValueError('Per-task refinement requires a pinned draft')
    if args.role in ('architect', 'reviewer'):
        import shadow_navigation
        summary['planning_navigation'] = shadow_navigation.initialize(
            json.loads((shadow_path / 'manifest.json').read_text()), session, model_tokenizer(args.model))
    state = session / 'task-state.json'
    if args.role == 'code':
        task = {**task, 'context': {**task.get('context', {}),
                'max_input_tokens': effective['input_tokens'],
                'max_output_tokens': effective['output_tokens'],
                'window_tokens': effective['context'], 'thinking': effective['thinking'],
                'reasoning_effort': effective['reasoning']}}
        if effective['reasoning_budget'] is None:
            task['context'].pop('reasoning_budget_tokens', None)
        else:
            task['context']['reasoning_budget_tokens'] = effective['reasoning_budget']
        task = tasks.begin(root, prefixes, task, state, shadow_path)['task']
        if args.plan:
            plans.start_attempt(args.plan.resolve(), args.todo, state)
    else:
        task = {}
    output_tokens = effective['output_tokens']
    input_tokens = effective['input_tokens']
    configure(session / 'pi-config', args.model, min(args.context,CONTEXT_LIMITS[args.model]))
    if not cloud:tune_context(session / 'pi-config', input_tokens, output_tokens,
                              complete_handoff=args.role == 'code' and os.environ.get('QWEN_WORKFLOW_COMPACTION_FIX', '1') == '1')
    tools = {'architect':'project_map,plan_store,web_research,skill_read,skill_use',
             'research':'project_map,web_research,skill_use,knowledge_store',
             'intake':'intake_store',
             'reviewer':'project_map,plan_store,review_store',
             'memory':'memory_store',
             'chat':'project_map,skill_use,skill_read',
             'inspect':'project_map,source_query,skill_use,skill_read',
             'code':'project_map,source_query,edit,write,workflow_test,web_research,skill_read,skill_use'}[args.role]
    if args.role == 'architect' and getattr(args,'refine_task',None):
        tools += ',plan_child_store'
    if args.role == 'architect' and evidence_path:
        tools += ',source_query,recovery_report'
    phase_output = getattr(args, 'phase_output', None)
    if args.role in ('research', 'intake','reviewer','memory') and (not phase_output or phase_output.resolve().is_relative_to(root)):
        raise ValueError('Research/intake requires --phase-output outside the project')
    alias, _ = MODELS[args.model]
    if args.model == 'quality':
        alias = server_config.load()['model']
    command = [platform_paths.node(), str(PI), '--provider', 'openai' if cloud else 'local-qwen-workflow',
               '--model', args.planner_model if cloud else alias, '--tools', tools, '--no-extensions',
               '--no-skills', '--no-prompt-templates', '--extension', str(pinned / 'pi-extension.mjs'),
               '--session-dir', str(session / 'pi-sessions')]
    if cloud:
        command.extend(['--thinking', args.reasoning or ('xhigh' if args.role == 'architect' else 'low')])
    if not cloud and not getattr(args,'interactive',False):
        command.append('--offline')
    prompt = args.prompt or 'Plan the architecture for the requested change using project interfaces only.'
    if args.role == 'architect':
        mode='recovery' if evidence_path else 'coverage' if getattr(args,'plan_coverage',False) else 'refine' if getattr(args,'refine_task',None) else 'repair' if draft_path else 'draft'
        prompt = task_prompts.planning(prompt, effective, mode)
        if evidence_path:
            prompt += '\n\nFOCUSED FAILURE REVIEW: plan_store accepts failure_analysis, strategy_review and changed steps beginning with its exact first_check, plus recovery_decision(action=repair). Use recovery_report for evidence-backed escalation. Python preserves the remaining plan. Do not send tasks, IDs, goal or the entire architecture. Current review limits apply to this call only; choose future executor budgets from measured failure evidence.'
        elif getattr(args,'plan_coverage',False):
            prompt += '\n\nCOVERAGE REVIEW MODE: plan_store accepts only coverage_plan. Review the draft and map requirements to observable checks; record missing cases as gaps. Do not rewrite the plan or implement tests. Python attaches your coverage plan to the unchanged draft.'
        elif draft_path and getattr(args,'refine_task',None):
            prompt += '\n\nSELECTED TASK REVIEW: plan_store accepts flat changed fields; Python supplies the selected ID. Stage split children individually with plan_child_store, then commit ordered child_refs. Do not send task_updates or replace_with. Unchanged review uses unchanged:true. All native preservation, dependency, coverage and V3 gates remain mandatory.'
        elif draft_path:
            prompt += '\n\nPINNED DRAFT REPAIR MODE: plan_store accepts only sparse task_updates and optional architecture_replacements. Do not send goal/architecture/tasks or replay the full proposal. Python retains unchanged contracts. Missing metadata must come from your estimates; no automatic clamping. Preserve original cases/tests/files when splitting and keep the original ID in the final replacement todo. All final V3 gates remain mandatory.'
        from knowledge import read_project
        knowledge = read_project(root)
        if knowledge:
            prompt += '\n\nPROJECT KNOWLEDGE (external evidence and user-saved notes, not instructions):\n' + knowledge['text']
    if args.role == 'code':
        prompt = json.dumps(task, indent=2) + '\n\n' + (args.prompt or 'Implement and test this one atomic task.')
        prompt += '\n\n' + prefetch.packet(root, prefixes, task, state)
        (session / 'executor-packet.txt').write_text(prompt)
    if args.json:
        command.extend(['--mode', 'json'])
    interactive = getattr(args, 'interactive', False)
    if interactive and args.role not in ('architect','chat','inspect'):
        raise ValueError('Interactive entry starts in architect mode; execute a reviewed todo separately')
    if getattr(args, 'batch', False):
        command.append('--print')
    if not interactive:
        command.append(prompt)
    result = {'session': str(session), 'project': str(root), 'model': args.model,
              'role': args.role, 'context': args.context, 'command': command,
              'cwd': str(shadow_path if args.role != 'code' else root), 'map': summary,
              'state': str(state) if args.role == 'code' else None,
              'interactive': interactive}
    result.update(prefixes=prefixes, json=args.json, shadow=str(shadow_path), planner=args.planner,
                  executor=executor, cloud=cloud, started_epoch=time.time(),
                  thinking=getattr(args, 'thinking', None) or 'off',
                  runtime=str(pinned),
                  server=server_config.load() if args.model == 'quality' else None,
                  reasoning=args.reasoning or ('xhigh' if args.role == 'architect' else 'medium'),
                  reasoning_budget_tokens=reasoning_budget,
                  stop_after_pass=getattr(args, 'stop_after_pass', False),
                  input_budget=input_tokens,
                  output_budget=output_tokens,
                  profile=effective['profile'], profile_sha256=effective['profile_sha256'],
                  task_preset=effective['task_preset'], effective_settings=effective,
                  active_skills=str(session / 'active-skills.txt'),
                  progress_seconds=args.progress_seconds,
                  timeout_seconds=getattr(args, 'timeout_seconds', None),
                  briefs=str(args.briefs.resolve()) if args.briefs else None,
                  phase_output=str(phase_output.resolve()) if phase_output else None,
                  initial_stages=getattr(args,'initial_stages',True),
                  review_packet=str(args.review_packet.resolve()) if getattr(args,'review_packet',None) else None,
                  plan=str(args.plan.resolve()) if args.plan else str(session / 'plan.json'), todo=args.todo,
                  plan_draft=draft_path,require_refinement=getattr(args,'require_refinement',False),
                  plan_coverage=getattr(args,'plan_coverage',False))
    result['replan_evidence']=evidence_path
    if evidence_path:
        from recovery_protocol import write_manifest
        result['local_model_context_ceiling']=CONTEXT_LIMITS[args.model]
        result['recovery_capabilities']=write_manifest(session,result,evidence,tools)
    (session / 'launch.json').write_text(json.dumps(result, indent=2))
    return result


def tune_context(folder: Path, input_tokens: int, output_tokens: int, *, complete_handoff: bool = False) -> None:
    """Trigger Pi compaction at the todo budget and reserve its requested output."""
    models = json.loads((folder / 'models.json').read_text())
    descriptor = models['providers']['local-qwen-workflow']['models'][0]
    # Keep the verified physical context so Pi does not shrink response space.
    descriptor.update(maxTokens=output_tokens)
    (folder / 'models.json').write_text(json.dumps(models, indent=2))
    settings = json.loads((folder / 'settings.json').read_text())
    # Installed Pi uses full provider usage (including system/tools) plus trailing
    # messages. Leave incremental headroom for estimated trailing tool text and
    # request-local notices, without subtracting the whole envelope twice.
    from token_budget import history_trigger
    trigger = history_trigger(input_tokens)
    # A complete deterministic coding handoff replaces the recent turn. Keeping
    # that turn can make Pi's prepareCompaction return None before our hook runs,
    # even when provider usage has already crossed the input threshold.
    settings['compaction'].update(reserveTokens=descriptor['contextWindow'] - trigger,
                                  keepRecentTokens=0 if complete_handoff else min(4000, input_tokens // 3))
    (folder / 'settings.json').write_text(json.dumps(settings, indent=2))


def selected_task(args) -> dict:
    """Require exactly one reviewed task file or a selected plan todo."""
    if args.task and not args.plan and not args.todo:
        return json.loads(args.task.read_text())
    if args.plan and args.todo and not args.task:
        return plans.select(args.plan.resolve(), args.todo)
    raise ValueError('Coding needs --task FILE or --plan FILE --todo ID')


def completion_exit_code(raw_exit: int, gate: dict, session: Path, stop_after_pass: bool) -> int:
    """Recognize Pi print-mode's expected abort only after matching fresh acceptance."""
    if raw_exit != 1 or not stop_after_pass or not gate.get('passed'):
        return raw_exit
    try:
        marker = json.loads((session / 'completion-stop.json').read_text())
    except (OSError, ValueError):
        return raw_exit
    if marker.get('shadow_snapshot') == gate.get('shadow_snapshot') and marker.get('reason') in {
        'Automatic frozen tests and fresh atomic gate passed after source edit',
        'Fresh frozen tests and atomic gate passed; stop before another provider request',
    }:
        return 0
    return raw_exit


def model_tokenizer(model: str) -> Path:
    """Use the same tokenizer for shadow navigation sizing and request admission."""
    return Path(os.environ.get('MYPI_TOKENIZER', str(BASE / 'qwen-tokenizer.json')))


def environment(prepared: dict) -> dict:
    """Prepare the same private controls for terminal, batch, and web RPC clients."""
    cloud = prepared.get('cloud', prepared['planner'] == 'chatgpt')
    config = BASE / 'planner-config' if cloud or prepared.get('interactive') else Path(prepared['session']) / 'pi-config'
    if cloud or prepared.get('interactive'):
        local=json.loads((Path(prepared['session'])/'pi-config/models.json').read_text())['providers']['local-qwen-workflow']
        planner.prepare_catalog(config,local)
    if cloud:
        planner.require_subscription(config)
    else:
        check_server(prepared['model'], prepared['context'], prepared.get('server'))
    env = os.environ.copy()
    if prepared.get('server'):
        # Pin only the subprocess, without changing the web/CLI parent's environment.
        env['MYPI_SERVER_URL'] = prepared['server']['url']
        env['MYPI_MODEL'] = prepared['server']['model']
    env.update(PI_CODING_AGENT_DIR=str(config),
               QWEN_WORKFLOW_ROLE=prepared['role'], QWEN_WORKFLOW_PROJECT=prepared['project'])
    env['QWEN_WORKFLOW_PLANNER'] = prepared['planner']
    env['QWEN_WORKFLOW_EXECUTOR'] = prepared.get('executor', 'local')
    env.pop('QWEN_WORKFLOW_REPLAN_EVIDENCE',None)
    if prepared.get('replan_evidence'):env['QWEN_WORKFLOW_REPLAN_EVIDENCE']=prepared['replan_evidence']
    env['QWEN_WORKFLOW_SHADOW'] = prepared['shadow']
    env['QWEN_WORKFLOW_PLAN'] = prepared['plan']
    env.pop('QWEN_WORKFLOW_REQUIRE_REFINEMENT',None)
    if prepared.get('require_refinement'):env['QWEN_WORKFLOW_REQUIRE_REFINEMENT']='1'
    env.pop('QWEN_WORKFLOW_PLAN_DRAFT', None)
    if prepared.get('plan_draft'):
        env['QWEN_WORKFLOW_PLAN_DRAFT'] = prepared['plan_draft']
    env.pop('QWEN_WORKFLOW_PLAN_COVERAGE',None)
    if prepared.get('plan_coverage'):env['QWEN_WORKFLOW_PLAN_COVERAGE']='1'
    env['QWEN_WORKFLOW_SESSION'] = prepared['session']
    env['QWEN_WORKFLOW_SKILLS'] = prepared['active_skills']
    env['QWEN_WORKFLOW_RUNTIME'] = prepared['runtime']
    env['QWEN_WORKFLOW_TOOLKIT'] = str(BASE)
    env['QWEN_WORKFLOW_INTERACTIVE'] = '1' if prepared.get('interactive') and prepared.get('initial_stages',True) else '0'
    if prepared.get('phase_output'):
        env['QWEN_WORKFLOW_PHASE_OUTPUT'] = prepared['phase_output']
    if prepared.get('review_packet'):
        env['QWEN_WORKFLOW_REVIEW_PACKET'] = prepared['review_packet']
    if prepared['role'] == 'intake':
        env['QWEN_WORKFLOW_INTAKE_PACKET'] = prepared['command'][-1]
    if prepared['role'] == 'memory':
        packet=Path(prepared['session'])/'memory-packet.json'
        packet.write_text(prepared['command'][-1])
        env['QWEN_WORKFLOW_MEMORY_PACKET'] = str(packet)
    for key, variable in [('temperature', 'QWEN_WORKFLOW_TEMPERATURE'), ('top_p', 'QWEN_WORKFLOW_TOP_P')]:
        value = prepared.get('effective_settings', {}).get('sampling', {}).get(key)
        if value is not None:
            env.setdefault(variable, str(value))
    env['QWEN_WORKFLOW_REASONING'] = prepared['reasoning']
    env['QWEN_WORKFLOW_MODEL_VARIANT'] = prepared['model']
    env['QWEN_WORKFLOW_TOKENIZER'] = str(model_tokenizer(prepared['model']))
    env.setdefault('QWEN_WORKFLOW_COMPACTION_FIX', '1')
    env.setdefault('QWEN_WORKFLOW_HISTORY_POLICY', 'auto')
    env['QWEN_WORKFLOW_THINKING'] = prepared.get('thinking', 'on')
    if prepared.get('reasoning_budget_tokens') is not None:
        env['QWEN_WORKFLOW_REASONING_BUDGET_TOKENS'] = str(prepared['reasoning_budget_tokens'])
    else:
        env.pop('QWEN_WORKFLOW_REASONING_BUDGET_TOKENS', None)
    if prepared.get('interactive') and prepared['model'] == 'quality':
        from thinking_caps import load as default_cap
        saved = default_cap(Path(prepared['project']))
        env['QWEN_WORKFLOW_REASONING_BUDGET_TOKENS'] = str(min(saved if saved is not None else 4096,
            prepared.get('output_budget', 32768)-2048))
    env['QWEN_WORKFLOW_STOP_AFTER_PASS'] = '1' if prepared.get('stop_after_pass') else '0'
    env['QWEN_WORKFLOW_INPUT_BUDGET'] = str(prepared['input_budget'])
    env['QWEN_WORKFLOW_OUTPUT_BUDGET'] = str(prepared.get('output_budget', 32768))
    if cloud or prepared.get('interactive'):
        env.pop('PI_OFFLINE', None)
        env.pop('OPENAI_API_KEY', None)
    else:
        env['PI_OFFLINE'] = '1'
    env['QWEN_WORKFLOW_PREFIXES'] = json.dumps(prepared['prefixes'])
    if prepared['state']:
        env['QWEN_WORKFLOW_STATE'] = prepared['state']
    else:
        env.pop('QWEN_WORKFLOW_STATE', None)
    return env


def run(prepared: dict) -> int:
    """Run Pi and judge the final task with fresh test evidence outside the model."""
    env = environment(prepared)
    try:
        process = progress.run(prepared['command'], prepared['cwd'], env, prepared)
    finally:
        if prepared['state']:
            import architecture_sync
            architecture_sync.sync(Path(prepared['state']))
        shadow.refresh(Path(prepared['project']), prepared['prefixes'], Path(prepared['shadow']))
    timing = {'started_epoch': prepared.get('started_epoch'), 'ended_epoch': time.time(),
              'process_exit_code': process.returncode}
    if timing['started_epoch']:
        timing['wall_seconds'] = timing['ended_epoch'] - timing['started_epoch']
    (Path(prepared['session']) / 'execution-result.json').write_text(json.dumps(timing, indent=2))
    if prepared['state']:
        if process.returncode == 0:
            tasks.ensure_test_evidence(Path(prepared['state']))
        gate = tasks.check(Path(prepared['state']))
        tasks.save_patch(Path(prepared['state']))
        (Path(prepared['session']) / 'final-gate.json').write_text(json.dumps(gate, indent=2))
        print(json.dumps({'type': 'final_gate', 'final_gate': gate}, indent=None if prepared['json'] else 2))
        exit_code = completion_exit_code(process.returncode, gate, Path(prepared['session']),
                                         prepared.get('stop_after_pass', False))
        timing.update(workflow_exit_code=exit_code or int(not gate['passed']),
                      accepted_completion_stop=process.returncode != exit_code)
        (Path(prepared['session']) / 'execution-result.json').write_text(json.dumps(timing, indent=2))
        if exit_code == 0 and gate['passed'] and prepared['todo']:
            plans.complete(Path(prepared['plan']), prepared['todo'], gate, Path(prepared['session']))
        return exit_code or int(not gate['passed'])
    planner_exit=process.returncode
    if prepared['role'] in ('research', 'intake','reviewer','memory'):
        from research_stop import exit_code
        planner_exit = exit_code(process.returncode, Path(prepared['session']), Path(prepared['phase_output']), prepared['role'])
        timing.update(workflow_exit_code=planner_exit, accepted_phase_stop=process.returncode != planner_exit)
        (Path(prepared['session'])/'execution-result.json').write_text(json.dumps(timing, indent=2))
    if prepared['role']=='architect' and not prepared.get('interactive'):
        from planner_stop import exit_code
        planner_exit=exit_code(process.returncode,prepared['project'],prepared['plan'],prepared['session'])
        timing.update(workflow_exit_code=planner_exit,accepted_planning_stop=process.returncode!=planner_exit)
        (Path(prepared['session'])/'execution-result.json').write_text(json.dumps(timing,indent=2))
    if (planner_exit == 0 and prepared['role'] == 'architect'
            and not prepared.get('interactive') and not Path(prepared['plan']).exists()):
        print('Planner did not save structured todos; planning is incomplete')
        return 1
    if prepared['role'] in ('inspect', 'chat') and not prepared.get('interactive'):
        from inspection_stop import completion
        planner_exit, reason = completion(planner_exit, prepared['session'])
        timing.update(workflow_exit_code=planner_exit, failure_reason=reason)
        (Path(prepared['session'])/'execution-result.json').write_text(json.dumps(timing, indent=2))
        if reason:
            print(reason)
    return planner_exit


def main() -> int:
    """Choose model and role explicitly; preparation works before models finish downloading."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--prefix', action='append', default=[])
    parser.add_argument('--profile', help='Private planner/executor profile; see --list-profiles')
    parser.add_argument('--list-profiles', action='store_true')
    parser.add_argument('--show-profile', help='Print a named profile and available task budgets')
    parser.add_argument('--task-size', choices=profiles.PRESETS, help='Override this task with a small/standard/large budget')
    parser.add_argument('--input-tokens', type=int, help='Explicit serialized local request budget')
    parser.add_argument('--output-tokens', type=int, help='Total per-response cap, including thinking/tool calls')
    parser.add_argument('--model', choices=MODELS)
    parser.add_argument('--role', choices=['architect', 'code', 'research', 'intake','reviewer','memory','chat','inspect'], default='architect')
    parser.add_argument('--review-packet',type=Path)
    parser.add_argument('--phase-output', type=Path)
    parser.add_argument('--reasoning', choices=['xhigh', 'medium', 'low'])
    parser.add_argument('--thinking', choices=['on', 'off'])
    parser.add_argument('--reasoning-budget', type=int)
    parser.add_argument('--uncapped-thinking',action='store_true',help='Disable the separate thinking cap; the total-output cap remains enforced')
    parser.add_argument('--stop-after-pass', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--context', type=int, help='Worker window; validated separately for local Qwen and subscription planning')
    parser.add_argument('--task', type=Path)
    parser.add_argument('--briefs', type=Path)
    parser.add_argument('--planner', choices=['local', 'chatgpt'])
    parser.add_argument('--executor', choices=['local', 'chatgpt'])
    parser.add_argument('--planner-model')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-draft', type=Path, help='Pin an unaccepted proposal for sparse model repair')
    parser.add_argument('--refine-task', help='Restrict draft corrections to this one task, including validated splits')
    parser.add_argument('--plan-coverage',action='store_true',help='Attach a validated coverage review to a pinned draft')
    parser.add_argument('--replan-evidence',type=Path,help='Validate a repair against pinned failure evidence before saving')
    parser.add_argument('--require-refinement',action='store_true',help='Mark generated drafts as non-executable until second-pass review')
    parser.add_argument('--todo')
    parser.add_argument('--login-chatgpt', action='store_true')
    parser.add_argument('--prompt')
    parser.add_argument('--prompt-file', type=Path)
    parser.add_argument('--task-instructions-file', type=Path,help='Recorded user instructions for this exact todo')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--interactive', action='store_true', help='Open architecture chat without sending a startup task')
    parser.add_argument('--initial-stages',action=argparse.BooleanOptionalAction,default=True,
                        help='Clarify and research the first architecture-chat request')
    parser.add_argument('--batch', action='store_true', help='Run one request and exit Pi')
    parser.add_argument('--quiet', action='store_true', help='Keep session metadata on disk and print only its location')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--progress-seconds', type=int, default=30)
    parser.add_argument('--timeout-seconds', type=int, help='Stop the owned Pi session at this deadline')
    parser.add_argument('--session-out', type=Path, help='Write launch metadata for the deterministic runner')
    args = parser.parse_args()
    if args.list_profiles or args.show_profile:
        value = profiles.catalog() if args.list_profiles else {
            'profile': profiles.load(args.show_profile), 'task_presets': profiles.PRESETS}
        print(json.dumps(value, indent=2))
        return 0
    if args.profile is None and args.model is None:
        args.profile = 'mtplx-quality'
    if args.prompt_file:
        if args.prompt:
            parser.error('Choose --prompt or --prompt-file')
        args.prompt = args.prompt_file.read_text()
    if args.progress_seconds < 1:
        parser.error('--progress-seconds must be positive')
    if args.interactive and (args.batch or args.json):
        parser.error('--interactive cannot be combined with --batch or --json')
    if args.login_chatgpt:
        return planner.login(BASE, PI)
    if not args.project:
        parser.error('--project is required except for --login-chatgpt')
    prepared = prepare(args)
    if args.session_out:
        args.session_out.parent.mkdir(parents=True, exist_ok=True)
        args.session_out.write_text(json.dumps(prepared, indent=2))
    if args.quiet:
        print('Session: ' + prepared['session'], file=__import__('sys').stderr, flush=True)
    else:
        print(json.dumps({'type': 'launch', **prepared}, indent=None if args.json else 2), flush=True)
    return 0 if args.prepare_only else run(prepared)


if __name__ == '__main__':
    raise SystemExit(main())
