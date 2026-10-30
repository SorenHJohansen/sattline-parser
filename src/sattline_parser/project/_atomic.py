"""Atomic sibling-file writes shared by the project caches.

Both caches write through a temporary file next to the target and then
``os.replace`` it into place. The temporary name must be unique per writer, or
two processes sharing a cache directory can truncate each other's file and a
concurrent prune can delete one that is still being written.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

__all__ = ["TEMP_SUFFIX", "temp_path_for"]

TEMP_SUFFIX = ".tmp"


def temp_path_for(path: Path) -> Path:
    """A unique sibling temporary path for ``path``, safe for concurrent writers."""
    return path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(8)}{TEMP_SUFFIX}")
