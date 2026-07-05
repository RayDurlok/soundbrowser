#!/usr/bin/env python3

"""Launcher script suitable for Resolve's Workspace -> Scripts menu."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def python_executable() -> str:
    if os.name == "nt":
        candidate = Path(sys.executable).with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    subprocess.Popen([python_executable(), str(project_root / "run.py")], close_fds=True)


if __name__ == "__main__":
    main()
