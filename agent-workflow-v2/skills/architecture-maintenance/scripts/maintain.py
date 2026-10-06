"""Perform native after-change maintenance for the immutable bound coding task."""
import json
from pathlib import Path
import sys
from architecture_update import binding
from architecture_maintenance import maintain
session = Path(sys.argv[1])
launch, state, contract, root = binding(session)
print(json.dumps(maintain(root, contract['before']['prefixes'], Path(contract['shadow']), state)))
