"""Project-local Qwen thinking defaults; explicit frozen task budgets win."""
import argparse
import fcntl
import json
from pathlib import Path
from role_selection import BASE, path_for
from runner_process import read, save


def load(project, base=BASE):
    """Return an optional validated default without changing project source."""
    value = read(path_for(project, base)).get('thinking_cap')
    if value is not None and (type(value) is not int or not 0 <= value <= 30720):
        raise ValueError('Invalid saved thinking cap')
    return value


def select(project, value, base=BASE):
    """Persist a bounded default atomically alongside independent role choices."""
    if value is not None and (type(value) is not int or not 0 <= value <= 30720):
        raise ValueError('Thinking cap must be 0..30720 or default')
    path = path_for(project, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = read(path)
        if value is None:
            data.pop('thinking_cap', None)
        else:
            data['thinking_cap'] = value
        save(path, data)
    return {'thinking_cap': value, 'scope': 'local Qwen defaults; explicit task caps take precedence'}


def main():
    """Allow private slash commands to inspect, set, or reset a default."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--value')
    args = parser.parse_args()
    result = {'thinking_cap': load(args.project)} if args.value is None else select(
        args.project, None if args.value == 'default' else int(args.value))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
