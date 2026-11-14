"""Atomic sibling-file writes shared by the project caches.

Both caches write through a temporary file next to the target and then
``os.replace`` it into place. The temporary name must be unique per writer, or
two processes sharing a cache directory can truncate each other's file and a
concurrent prune can delete one that is still being written.
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

__all__ = ["TEMP_FILE_MAX_AGE_SECONDS", "TEMP_SUFFIX", "temp_file_is_abandoned", "temp_path_for"]

TEMP_SUFFIX = ".tmp"

#: A temporary file younger than this may belong to a running writer, so a
#: cleanup pass leaves it alone.
TEMP_FILE_MAX_AGE_SECONDS = 3600.0


def temp_path_for(path: Path) -> Path:
    """A unique sibling temporary path for ``path``, safe for concurrent writers."""
    return path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(8)}{TEMP_SUFFIX}")


def temp_file_is_abandoned(path: Path) -> bool:
    """True when a temporary file is old enough that no writer can still own it."""
    try:
        stat_result = path.stat()
    except OSError:
        return True
    return time.time() - stat_result.st_mtime >= TEMP_FILE_MAX_AGE_SECONDS
