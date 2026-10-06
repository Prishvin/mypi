#!/bin/sh
set -eu
mypi_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$mypi_root"
python_bin=${MYPI_PYTHON:-python3}
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 12), "mypi requires Python 3.12 or newer (set MYPI_PYTHON if needed)"'
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22 || (a===22 && b<19))throw Error("Node >=22.19 is required")'
command -v git >/dev/null
command -v rg >/dev/null
command -v ps >/dev/null
"$python_bin" -m venv agent-workflow-v2/.venv
agent-workflow-v2/.venv/bin/python -m pip install -r requirements.txt
npm ci --ignore-scripts
mkdir -p "$HOME/.local/bin"
ln -sf "$mypi_root/mypi" "$HOME/.local/bin/mypi"
printf '\nInstalled mypi. Add ~/.local/bin to PATH. Default server: localhost:8000.\n  mypi server SERVER_IP:8000\n  mypi chat /path/to/project\n'
