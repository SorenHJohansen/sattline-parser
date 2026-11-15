"""Process-pool shaping shared by the project loader and the batch CLI.

A pool's start method decides both safety and portability. Forking a process
that holds other threads is deprecated in CPython and can inherit a lock another
thread held at fork time, so a threaded host uses ``forkserver`` and then
``spawn``. A single-threaded host on Linux before Python 3.14 may use ``fork``,
which needs no ``__main__`` guard, and every other case keeps the platform
default.

The helpers here are implementation details of the package. They are importable
so the project loader and the CLI share one rule instead of two.
"""

from __future__ import annotations

import multiprocessing
import sys
import threading
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor

__all__ = ["pool_allowed", "process_pool", "start_method"]


def start_method(
    methods: Sequence[str],
    *,
    threaded: bool,
    platform: str = sys.platform,
    version: tuple[int, int] = sys.version_info[:2],
) -> str | None:
    """The preferred pool start method, or ``None`` for the platform default.

    A single-threaded process on Linux before Python 3.14 prefers ``fork``: the
    caller needs no ``__main__`` guard. Forking a process with other threads is
    deprecated in CPython and can inherit a lock another thread held at fork
    time, so a threaded host prefers ``forkserver``, then ``spawn``. Python 3.14
    moved the Linux default away from ``fork`` for the same reason, and macOS
    defaults to ``spawn``, so both keep the platform default instead of forcing
    ``fork``. Platforms that offer only ``fork`` still get it through that
    default: this is a preference, not a guarantee.
    """
    if threaded:
        for candidate in ("forkserver", "spawn"):
            if candidate in methods:
                return candidate
    if not threaded and platform.startswith("linux") and version < (3, 14) and "fork" in methods:
        return "fork"
    return None


def pool_allowed() -> bool:
    """Whether this process may start children.

    A daemonic process may not, so a caller inside an outer pool has to do the
    work itself rather than raise.
    """
    return not multiprocessing.current_process().daemon


def process_pool(max_workers: int) -> ProcessPoolExecutor:
    """A process pool shaped for the current process."""
    method = start_method(multiprocessing.get_all_start_methods(), threaded=threading.active_count() > 1)
    return ProcessPoolExecutor(max_workers=max_workers, mp_context=multiprocessing.get_context(method))
