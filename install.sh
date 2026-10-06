#!/bin/sh
set -eu
mypi_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$mypi_root"
printf 'Checking mypi prerequisites...\n'
if [ -n "${SUDO_USER:-}" ]; then
  printf 'Run ./install.sh without sudo. It installs into this checkout and your user account; sudo can select an older system Node.\n' >&2
  exit 1
fi
python_bin=${MYPI_PYTHON:-python3}
if ! command -v "$python_bin" >/dev/null 2>&1; then
  printf 'Python is missing. Install Python 3.12+, then rerun ./install.sh (or set MYPI_PYTHON).\n' >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  printf 'Node is missing. Install Node 22.19+ and npm, then rerun ./install.sh.\n' >&2
  exit 1
fi
"$python_bin" -c 'import sys; sys.exit("Python " + sys.version.split()[0] + " is too old: mypi requires Python 3.12+. Select it with MYPI_PYTHON=python3.12 ./install.sh.") if sys.version_info < (3, 12) else None'
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22 || (a===22 && b<19)){console.error("Node " + process.versions.node + " is too old: mypi requires Node 22.19+. Upgrade Node (for example: nvm install 24 && nvm use 24), then rerun ./install.sh without sudo.");process.exit(1)}'
for mypi_tool in npm git rg ps; do
  if ! command -v "$mypi_tool" >/dev/null 2>&1; then
    printf 'Missing prerequisite: %s. Install npm, Git, ripgrep (rg) and procps (ps), then rerun ./install.sh.\n' "$mypi_tool" >&2
    exit 1
  fi
done
printf 'Creating the private Python environment...\n'
if [ -d agent-workflow-v2/.venv ] && ! agent-workflow-v2/.venv/bin/python -c 'import sys' >/dev/null 2>&1; then
  mypi_venv_action=--clear
else
  mypi_venv_action=
fi
if ! "$python_bin" -m venv $mypi_venv_action agent-workflow-v2/.venv; then
  printf 'Could not create the Python environment. On Ubuntu/Debian, install the matching Python venv package (for example python3.12-venv). Rerun ./install.sh without sudo.\n' >&2
  exit 1
fi
printf 'Installing Python dependencies...\n'
agent-workflow-v2/.venv/bin/python -m pip install -r requirements.txt
printf 'Installing Pi dependencies...\n'
npm ci --ignore-scripts
mkdir -p "$HOME/.local/bin"
ln -sf "$mypi_root/mypi" "$HOME/.local/bin/mypi"
printf '\nInstalled mypi. Add ~/.local/bin to PATH. Default server: localhost:8000.\n  mypi server SERVER_IP:8000\n  mypi chat /path/to/project\n'
