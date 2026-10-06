#!/bin/sh
set -eu
mypi_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python_bin=${MYPI_PYTHON:-python3.12}
if ! command -v "$python_bin" >/dev/null 2>&1; then python_bin=python3; fi
exec "$python_bin" "$mypi_root/qwen-host/setup.py" "$@"
