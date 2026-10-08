"""Publish an evidence-bound recovery escalation without editing or executing a task."""
import argparse
import json
from pathlib import Path
import time
from plan_draft import digest
from project_map import scan
from recovery_protocol import validate
from runner_process import read, save


def binding(session):
    """Bind reports to this launched failure review and its current source snapshot."""
    session = Path(session).resolve()
    launch = read(session / 'launch.json')
    evidence = session / 'replan-evidence.json'
    if (launch.get('role') != 'architect' or launch.get('session') != str(session)
            or launch.get('replan_evidence') != str(evidence)):
        raise ValueError('Recovery reports require a bound failure-recovery session')
    packet = read(evidence)
    root = Path(launch['project']).resolve()
    if (packet.get('project') != str(root) or
            packet.get('current_snapshot') != scan(root, ['.'])['snapshot']):
        raise ValueError('Recovery report source evidence is stale or belongs to another project')
    if packet.get('recovery_plan_sha256') != digest(read(Path(packet['plan']))):
        raise ValueError('Original recovery plan changed')
    return launch, packet


def store(session, decision):
    """Only explicit escalations produce a stop receipt; never a successful plan."""
    session = Path(session).resolve()
    launch, packet = binding(session)
    decision = validate(decision, packet)
    if not decision or decision['action'] == 'repair':
        raise ValueError('A corrective plan must use plan_store, not recovery_report')
    if Path(launch['plan']).exists() or (session / 'planning-stop.json').exists():
        raise ValueError('A plan was already published; cannot replace it with escalation')
    destination = session / 'recovery-report.json'
    if destination.exists():
        raise ValueError('A recovery report is already published')
    record = {'project': launch['project'], 'evidence_sha256': digest(packet),
              'decision': decision, 'finished_epoch': time.time()}
    save(destination, record)
    return record


def verified(session):
    """Recheck a stored stop before terminating its process or surfacing the decision."""
    try:
        launch, packet = binding(session)
        record = read(Path(session) / 'recovery-report.json')
        if (record.get('project') != launch['project'] or record.get('evidence_sha256') != digest(packet)
                or Path(launch['plan']).exists() or not isinstance(record.get('finished_epoch'), (int, float))):
            return None
        decision = validate(record.get('decision'), packet)
        return record if decision and decision['action'] != 'repair' else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(store(args.session, json.loads(args.input.read_text()))))
