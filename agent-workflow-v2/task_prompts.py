"""Build architectural requests without adding implementation source."""
from pathlib import Path


def planning(request: str, settings: dict, mode='draft') -> str:
    """Wrap a feature request in the granular plan contract and current role budget."""
    if mode not in ('draft','repair','coverage','refine','recovery'):
        raise ValueError('Unknown planning prompt mode: '+mode)
    if mode != 'draft':
        contract = ('failure_analysis, strategy_review and changed steps for the failed task only, plus recovery_decision(action=repair); use recovery_report to escalate' if mode=='recovery' else
                    'coverage_plan only; preserve the pinned tasks' if mode=='coverage' else
                    'flat changed fields or staged child_refs for the selected task' if mode=='refine' else
                    'sparse task_updates and optional architecture_replacements only')
        return (f'REVIEW THE PINNED PLAN ({mode}). This session has {settings["context"]} tokens of capacity.\n'
                f'plan_store accepts {contract}. Do not create a replacement whole plan.\n'
                'Follow the review packet and current tool schema. No implementation is authorized.\n\n'+request)
    template = Path(__file__).with_name('prompts').joinpath('create-plan.txt').read_text()
    return template.replace('{{REQUEST}}', request).replace('{{CONTEXT}}', str(settings['context']))
