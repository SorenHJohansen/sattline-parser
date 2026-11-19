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
import os
import sys
import threading
from collections.abc import Generator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager

__all__ = [
    "POOL_WORKER_ENV",
    "load_in_progress",
    "loads_in_progress",
    "pool_allowed",
    "process_pool",
    "start_method",
]

#: Environment marker set in every worker of a pool this module starts. A
#: ``ProcessPoolExecutor`` worker is not daemonic, so the daemon flag alone does
#: not say that it already belongs to an outer pool. The marker survives fork
#: and spawn, and a load that runs in a worker therefore parses in place instead
#: of multiplying the process count.
POOL_WORKER_ENV = "SATTLINE_PARSER_POOL_WORKER"

#: Per-thread count of loads that are resolving. A load constructed while one is
#: already running is nested by definition, even in a process that may otherwise
#: start children.
_LOAD_STATE = threading.local()

_POOL_WORKER_VALUE = "1"


def _mark_pool_worker() -> None:
    """Mark this process as one of a parser pool's workers."""
    os.environ[POOL_WORKER_ENV] = _POOL_WORKER_VALUE


def loads_in_progress() -> int:
    """How many loads are resolving on this thread."""
    return int(getattr(_LOAD_STATE, "depth", 0))


@contextmanager
def load_in_progress() -> Generator[None]:
    """Mark that a load is resolving on this thread for the duration."""
    _LOAD_STATE.depth = loads_in_progress() + 1
    try:
        yield
    finally:
        _LOAD_STATE.depth -= 1


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


def pool_allowed(*, nested: bool = False) -> bool:
    """Whether this process may start a parser pool.

    A daemonic process may not start children, a process that is itself a child
    of another process already belongs to a pool, and a process carrying this
    module's worker marker is one of its own workers. A load constructed while
    another load is resolving on this thread is nested and must not multiply the
    process count either. In every one of those cases the caller parses in place
    instead of raising; *nested* is the loader's answer to the last question,
    decided when the loader is constructed.
    """
    return (
        not nested
        and not multiprocessing.current_process().daemon
        and multiprocessing.parent_process() is None
        and os.environ.get(POOL_WORKER_ENV) != _POOL_WORKER_VALUE
    )


def process_pool(max_workers: int) -> ProcessPoolExecutor:
    """A process pool shaped for the current process.

    Every worker is marked with :data:`POOL_WORKER_ENV` before it runs a task, so
    a load that somehow runs inside one does not start a second pool.
    """
    method = start_method(multiprocessing.get_all_start_methods(), threaded=threading.active_count() > 1)
    return ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=multiprocessing.get_context(method),
        initializer=_mark_pool_worker,
    )
