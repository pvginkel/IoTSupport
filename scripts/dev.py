#!/usr/bin/env python3
"""Start all dev services via honcho (process manager).

Usage:
    ./scripts/dev.py              # start all services (backend + frontend)
    ./scripts/dev.py -e frontend  # start all except the frontend

Reads the repo-root Procfile.dev. Per-service logs (ANSI-stripped) are written
to logs/<service>.log. Ctrl-C stops everything cleanly.

All child processes run inside a PID namespace (via unshare --user --pid --fork)
so the kernel unconditionally kills every descendant when honcho exits.

Note: the backend requires its Poetry venv to be on Python 3.13 (run
scripts/build-all.py or scripts/preflight.py once to pin it via
`poetry env use python3.13`). The SSE gateway (frontend proxy target :3102) is
not in Procfile.dev — start it separately when you need SSE-backed features.
"""

import os
import re
import signal
import sys
from pathlib import Path

import pty

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"

ANSI_RE = re.compile(rb"\x1b\[[0-9;]*[a-zA-Z]")

# Honcho prefixes lines like: '19:05:11 backend.1  | ...'
# Extract the service name to route to per-service log files.
PREFIX_RE = re.compile(rb"^\d{2}:\d{2}:\d{2}\s+(\S+)\s+\|")

log_files: dict[bytes, "io.BufferedWriter"] = {}
buf = b""


def get_log(service: bytes) -> "io.BufferedWriter":
    if service not in log_files:
        name = service.rsplit(b".", 1)[0]  # 'backend.1' -> 'backend'
        log_files[service] = open(LOGS / (name.decode() + ".log"), "wb")
    return log_files[service]


def read(fd: int) -> bytes:
    global buf
    data = os.read(fd, 4096)
    buf += data

    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        stripped = ANSI_RE.sub(b"", line)
        m = PREFIX_RE.match(stripped)
        if m:
            log = get_log(m.group(1))
            # Strip the honcho prefix, keep only the service's own output
            content = stripped[stripped.index(b"| ") + 2 :]
            log.write(content + b"\n")
            log.flush()

    return data


def main() -> None:
    LOGS.mkdir(exist_ok=True)
    os.chdir(ROOT)

    # Force colors in subprocesses — honcho pipes their output, so they
    # don't see a TTY. These env vars re-enable colors for common tools.
    os.environ["FORCE_COLOR"] = "1"  # Node.js / chalk / Vite
    os.environ["PY_COLORS"] = "1"  # Python tools that check this

    # Ignore signals in this process — let honcho handle them.
    # When honcho exits, the PID namespace ensures all children are killed.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

    # Run honcho inside a PTY (for colors) and a PID namespace (for cleanup).
    status = pty.spawn(
        ["unshare", "--user", "--pid", "--fork",
         "poetry", "run", "honcho", "start", "-f", "Procfile.dev"] + sys.argv[1:],
        read,
    )

    for f in log_files.values():
        f.close()

    exit_code = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else status >> 8
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
