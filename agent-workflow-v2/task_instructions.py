"""Keep user-authored task instructions outside source and frozen contracts."""
from pathlib import Path
from runner_process import read, save


def coordinator(folder):
    """Find the owning recovery run without traversing arbitrary ancestors."""
    return folder if (folder/'recovery-state.json').exists() else folder.parent if (folder.parent/'recovery-state.json').exists() else folder


def original(task):
    """Render the editable strategy while leaving tests and scope in the contract."""
    return task['goal']+'\n\n'+'\n'.join(str(i+1)+'. '+s for i,s in enumerate(task.get('steps',[])))


def current(folder, task):
    """Return the latest explicit user instruction for this todo, if any."""
    row=read(coordinator(folder)/'task-instructions'/f"{task['id']}.json")
    return row.get('prompt',original(task))


def prompt_file(folder, task, resume=None):
    """Add a user's revised strategy to a fresh attempt, never replay old messages."""
    owner=coordinator(folder);row=read(owner/'task-instructions'/f"{task['id']}.json")
    if not row:return resume
    if row.get('todo')!=task['id']:raise ValueError('Task instruction identity mismatch')
    text=Path(resume).read_text() if resume else ''
    text+='\n\nUSER TASK INSTRUCTIONS (latest user revision):\n'+row['prompt']
    text+='\nThese instructions supersede earlier strategy prose. Preserve the frozen file scope, acceptance, tests and completed work. If incompatible, stop for evidence-based replanning.'
    output=folder/f"user-prompt-{task['id']}.txt";output.write_text(text)
    return str(output)


def instruction_file(folder, task):
    """Return the local directive artifact to preserve through deterministic compaction."""
    path=coordinator(folder)/'task-instructions'/f"{task['id']}.json"
    return path if path.is_file() else None
