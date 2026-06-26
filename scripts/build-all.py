#!/usr/bin/env python3
"""Build all components of the IoTSupport monorepo.

Customize the STEPS list for your project. Each entry is:
    (component_label, action_description, command_argv, working_directory)

Add or remove rows so this script installs/builds every subproject your
slices depend on. The /run-slice pre-flight invokes this script to catch
dependency drift and broken builds before any dev agent starts.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from _initd_log import run_step

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
FRONTEND = REPO_ROOT / "frontend"

# The backend requires Python 3.13 (e.g. queue.ShutDown). When a python3.13
# interpreter is on PATH, pin the backend's Poetry venv to it; in CI the base
# image's default python is already 3.13 (the binary may be absent by that
# name), so this step is skipped there.
STEPS: list[tuple[str, str, list[str], Path]] = [
    ("root", "poetry install", ["poetry", "install", "--no-interaction"], REPO_ROOT),
]
if shutil.which("python3.13"):
    STEPS.append(
        ("backend", "poetry env use python3.13", ["poetry", "env", "use", "python3.13"], BACKEND)
    )
STEPS += [
    ("backend", "poetry install", ["poetry", "install", "--no-interaction"], BACKEND),
    # The frontend is a standalone pnpm project (its own lockfile), not a
    # workspace member — install it in its own directory.
    (
        "frontend",
        "pnpm install",
        ["pnpm", "install", "--frozen-lockfile", "--config.confirmModulesPurge=false"],
        FRONTEND,
    ),
    ("frontend", "pnpm build", ["pnpm", "build"], FRONTEND),
]


def main() -> int:
    for component, action, cmd, cwd in STEPS:
        if run_step(component, action, cmd, cwd) != 0:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
