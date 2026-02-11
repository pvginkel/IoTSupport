"""Filesystem utilities."""

import os
import tempfile
from pathlib import Path


def atomic_write(target_path: Path, content: bytes, staging_dir: Path) -> None:
    """Write content atomically using a temp file and rename.

    Creates a temporary file in staging_dir, writes content, then
    atomically replaces target_path via os.replace(). If any step fails,
    the temp file is cleaned up and the exception propagates.

    Args:
        target_path: Final destination path
        content: Bytes to write
        staging_dir: Directory for the temporary file (must be on the same
            filesystem as target_path for os.replace to work)
    """
    fd, temp_path = tempfile.mkstemp(dir=staging_dir, suffix=".tmp")
    try:
        os.write(fd, content)
        os.close(fd)
        os.replace(temp_path, target_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
