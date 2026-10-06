"""Resolve client executables without assuming a user name or Homebrew layout."""
import os
from pathlib import Path
import shutil


def node() -> str:
    """Find Node on either supported platform, allowing an explicit override."""
    value = os.environ.get('MYPI_NODE') or shutil.which('node')
    if not value:
        raise ValueError('Node >=22.19 is required; run ./install.sh after installing Node')
    return value


def pi(base: Path) -> Path:
    """Use the repo-local locked dependency unless a caller explicitly supplies Pi."""
    return Path(os.environ.get('MYPI_PI', str(base.parent / 'node_modules/.bin/pi')))
