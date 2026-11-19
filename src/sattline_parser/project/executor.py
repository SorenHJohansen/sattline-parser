"""The parse phase: turn plans into parsed bodies, in workers when asked.

This module owns everything about parsing a planned body: the process pool, the
worker task, the picklable failure record, the AST cache, and the in-process
path. It never discovers, assembles, or validates, so its failure modes are the
ones that belong to reading and parsing a file.

A failure is carried back as data, not raised, because only the assembly phase
knows which dependency edge and which owning unit the message should name.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any, cast

from lark import Token
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

from sattline_parser.errors import PARSE_FAILURES, SourceTooDeepError
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.preprocessing.compressed import PreprocessError
from sattline_parser.source_io import parse_source_bytes

from .ast_cache import FileASTCache, SourceSnapshot, source_snapshot
from .errors import ArtifactLoadError, DependencyParseError, ProjectLoadError
from .models import LoadMode
from .parallel import pool_allowed
from .plan import Plan

__all__ = [
    "ParseExecutor",
    "ParseFailure",
    "ParseOutcome",
    "parse_code_file",
    "rebuild_parse_failure",
]

_LOGGER = getLogger(__name__)

#: OSError subclasses a worker can report. The subclass carries meaning for the
#: caller (a permission problem, a vanished file, a directory where a file was
#: expected), so the parent rebuilds the same type instead of collapsing it.
_OSERROR_TYPES: dict[str, type[OSError]] = {
    "BlockingIOError": BlockingIOError,
    "BrokenPipeError": BrokenPipeError,
    "ChildProcessError": ChildProcessError,
    "ConnectionAbortedError": ConnectionAbortedError,
    "ConnectionError": ConnectionError,
    "ConnectionRefusedError": ConnectionRefusedError,
    "ConnectionResetError": ConnectionResetError,
    "FileExistsError": FileExistsError,
    "FileNotFoundError": FileNotFoundError,
    "InterruptedError": InterruptedError,
    "IsADirectoryError": IsADirectoryError,
    "NotADirectoryError": NotADirectoryError,
    "OSError": OSError,
    "PermissionError": PermissionError,
    "ProcessLookupError": ProcessLookupError,
    "TimeoutError": TimeoutError,
}


@dataclass(frozen=True, slots=True)
class ParseFailure:
    """A picklable description of a parse failure raised in a worker.

    The exception object itself is not sent across the process boundary: Lark
    exceptions carry parser state and tokens. The record keeps the facts the
    parent needs to rebuild the same exception type and source position.
    """

    type_name: str
    message: str
    line: int | None = None
    column: int | None = None
    pos_in_stream: int | None = None
    token_type: str | None = None
    token_value: str | None = None
    expected: tuple[str, ...] = ()
    char: str | None = None
    limit: int | None = None
    unicode_error: tuple[str, bytes, int, int, str] | None = None


@dataclass(frozen=True, slots=True)
class ParseOutcome:
    """A parsed body, or the text of the failure that stopped it."""

    ast: BasePicture | None = None
    failure: str | None = None
    #: The original parse failure, kept when the parse ran in this process so a
    #: caller can still reach a ``SourceTooDeepError`` limit or a decode
    #: offset through ``__cause__``. A worker returns ``failure_record``.
    error: BaseException | None = None
    failure_record: ParseFailure | None = None
    #: The exact source revision the worker parsed, so the parent can refuse to
    #: cache an AST when the file changed while the worker was reading it.
    snapshot: SourceSnapshot | None = None
    #: The AST came from the cache, so it has nothing to store.
    cached: bool = False


def parse_failure_record(exc: BaseException) -> ParseFailure:
    """Describe *exc* without pickling parser state."""
    token = getattr(exc, "token", None)
    expected = getattr(exc, "expected", None) or getattr(exc, "allowed", ())
    unicode_error = (
        (exc.encoding, exc.object, exc.start, exc.end, exc.reason) if isinstance(exc, UnicodeDecodeError) else None
    )
    return ParseFailure(
        type_name=type(exc).__name__,
        message=str(exc) or type(exc).__name__,
        line=_optional_int(getattr(exc, "line", None)),
        column=_optional_int(getattr(exc, "column", None)),
        pos_in_stream=_optional_int(getattr(exc, "pos_in_stream", None)),
        token_type=str(token.type) if isinstance(token, Token) else None,
        token_value=str(token) if isinstance(token, Token) else None,
        expected=tuple(sorted(str(item) for item in expected)),
        char=getattr(exc, "char", None),
        limit=_optional_int(getattr(exc, "limit", None)),
        unicode_error=unicode_error,
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def rebuild_parse_failure(record: ParseFailure) -> BaseException:
    """Rebuild a worker failure so ``__cause__`` matches an in-process parse."""
    line = record.line if record.line is not None else 1
    column = record.column if record.column is not None else 1
    pos = record.pos_in_stream if record.pos_in_stream is not None else 0
    if record.unicode_error is not None:
        return UnicodeDecodeError(*record.unicode_error)
    if record.type_name == "SourceTooDeepError" and record.limit is not None:
        return SourceTooDeepError(
            record.limit,
            line=record.line,
            column=record.column,
            pos_in_stream=record.pos_in_stream,
        )
    if record.type_name == "UnexpectedToken" and record.token_type is not None:
        token = Token(record.token_type, record.token_value or "")
        token.line = line
        token.column = column
        token.start_pos = pos
        token.end_pos = pos + len(str(token))
        return UnexpectedToken(token, list(record.expected))
    if record.type_name == "UnexpectedCharacters":
        sequence = " " * pos + (record.char or " ")
        return UnexpectedCharacters(sequence, pos, line, column, allowed=list(record.expected) or None)
    if record.type_name == "UnexpectedEOF":
        return UnexpectedEOF(list(record.expected))
    if record.type_name == "UnexpectedInput":
        error = UnexpectedInput(record.message)
        error.line = line
        error.column = column
        cast(Any, error).pos_in_stream = pos
        return error
    if record.type_name == "PreprocessError":
        return PreprocessError(record.message)
    if record.type_name in {"UnicodeError", "UnicodeDecodeError"}:
        return UnicodeError(record.message)
    if record.type_name == "ValueError":
        return ValueError(record.message)
    error_type = _OSERROR_TYPES.get(record.type_name)
    if error_type is not None:
        # Preserve the subclass: the assembler chains this as the cause, and a
        # PermissionError or FileNotFoundError tells the operator what happened.
        return error_type(record.message)
    return RuntimeError(record.message)


#: One cache handle per worker process. Constructing a handle per task would
#: re-run the private-directory check for every file, and the handle is
#: read-only so a worker never prunes, touches, or writes an entry.
_WORKER_CACHES: dict[str, FileASTCache] = {}


def _worker_cache(cache_text: str) -> FileASTCache:
    cache = _WORKER_CACHES.get(cache_text)
    if cache is None:
        cache = FileASTCache(Path(cache_text), read_only=True)
        _WORKER_CACHES[cache_text] = cache
    return cache


def parse_code_file(
    task: tuple[str, str, str | None, bool],
    *,
    parse_bytes: Callable[..., BasePicture] | None = None,
    snapshot: Callable[..., SourceSnapshot | None] | None = None,
) -> ParseOutcome:
    """Parse one code file into an AST.

    Runs in a child process when ``workers`` is greater than one, so it must not
    touch the loader or its registry. It reads the AST cache through a read-only
    handle and never writes it: the parent owns every write, so the per-user
    cache key is created and the entries are signed by a single process, and a
    worker neither prunes an entry nor moves its mtime. A failure comes back as
    text, because the error type and wording depend on the dependency edge and
    the parent owns both. ``log_failures`` mirrors the parent's choice: a plain
    load keeps stderr for the structured finding, and ``--debug`` keeps the
    parser traceback.
    """
    if parse_bytes is None:
        parse_bytes = parse_source_bytes
    if snapshot is None:
        snapshot = source_snapshot
    code_text, mode, cache_text, log_failures = task
    code_path = Path(code_text)
    if cache_text is not None:
        cached = _worker_cache(cache_text).load(code_path, mode)
        if cached is not None:
            return ParseOutcome(ast=cached, cached=True)
    try:
        raw_bytes = code_path.read_bytes()
    except OSError as exc:
        return ParseOutcome(failure=str(exc), failure_record=parse_failure_record(exc))
    source_revision = snapshot(code_path, raw_bytes)
    try:
        picture = parse_bytes(raw_bytes, source_path=code_path, log_failures=log_failures)
    except PARSE_FAILURES as exc:
        return ParseOutcome(
            failure=str(exc) or type(exc).__name__,
            failure_record=parse_failure_record(exc),
        )
    return ParseOutcome(ast=picture, snapshot=source_revision)


class ParseExecutor:
    """Parse every planned body, in this process or in a worker pool.

    The executor owns the outcomes and the AST cache. It is constructed with the
    pool factory so a caller can substitute a fake pool without reaching into
    module globals.
    """

    def __init__(
        self,
        *,
        mode: LoadMode,
        workers: int,
        log_failures: bool,
        debug: Callable[[str], None] | None,
        ast_cache: FileASTCache | None,
        secure_cache_dir: Path | None,
        pool_factory: Callable[[int], ProcessPoolExecutor],
        nested: bool = False,
    ) -> None:
        self._mode = mode
        self._workers = max(1, workers)
        self._log_failures = log_failures
        self._debug = debug
        self._ast_cache = ast_cache
        self._secure_cache_dir = secure_cache_dir
        self._pool_factory = pool_factory
        #: Whether this load was constructed inside another load's resolve. A
        #: nested load parses in place: a second pool would multiply processes.
        self._nested = nested
        #: Plan key -> the parsed body or the failure that stopped it.
        self.outcomes: dict[str, ParseOutcome] = {}

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    def parse(self, plans: Sequence[Plan]) -> dict[str, ParseOutcome]:
        """Parse *plans* and return their outcomes, keyed by plan key."""
        self._parse_planned(plans)
        return self.outcomes

    def _parse_planned(self, plans: Sequence[Plan]) -> None:
        """Parse every planned body, in parallel when ``workers`` allows it.

        A failure is carried to the assembly phase, which raises it with the
        dependency edge and the unit name that the worker cannot know.
        """
        if not plans:
            return
        if self._workers <= 1 or len(plans) == 1:
            for plan in plans:
                self.outcomes[plan.key] = self._parse_in_process(plan)
            return
        if not pool_allowed(nested=self._nested):
            # A daemonic process cannot start children, and a process that is
            # already part of an outer pool must not multiply the process count.
            # Parsing here is slower but correct, and the caller already owns a
            # pool to run us on. Say so once, not per body: a silent serial load
            # looks like a clean parallel one.
            _LOGGER.warning(
                "worker pool not started (nested load or outer pool); parsing %d bodies in this process instead",
                len(plans),
            )
            self._dbg("Parsing in this process: this process may not start a worker pool")
            for plan in plans:
                self.outcomes[plan.key] = self._parse_in_process(plan)
            return

        cache_text = None if self._secure_cache_dir is None else str(self._secure_cache_dir)
        tasks = [(str(plan.artifact.code_path), self._mode.value, cache_text, self._log_failures) for plan in plans]
        workers = min(self._workers, len(tasks))
        self._dbg(f"Parsing {len(tasks)} bodies in {workers} processes")
        try:
            pool = self._pool_factory(workers)
        except (OSError, RuntimeError, ValueError) as exc:
            # A pool cannot always be created (no worker start method, a
            # restricted sandbox). Parsing is the load, not an optimisation
            # detail, so fall back to this process rather than failing. The
            # warning is not gated on --debug: a serial load is a real
            # performance regression the operator should see.
            _LOGGER.warning(
                "worker pool unavailable (%s); parsing %d bodies in this process instead",
                exc,
                len(plans),
            )
            self._dbg(f"Parallel parsing unavailable ({exc}); parsing in this process")
            for plan in plans:
                self.outcomes[plan.key] = self._parse_in_process(plan)
            return
        try:
            outcomes = list(pool.map(parse_code_file, tasks, chunksize=1))
        except (BrokenProcessPool, OSError) as exc:
            # ``ProcessPoolExecutor`` starts its workers on the first submit, so
            # a missing worker start method, a denied fork, or an exhausted
            # process limit surfaces here rather than from the constructor. A
            # dead worker is the same story. Parsing is the load, not an
            # optimisation detail, so fall back to this process.
            pool.shutdown(wait=True, cancel_futures=True)
            _LOGGER.warning(
                "worker pool failed (%s); parsing %d bodies in this process instead",
                exc,
                len(plans),
            )
            self._dbg(f"Worker pool failed ({exc}); parsing in this process")
            for plan in plans:
                self.outcomes[plan.key] = self._parse_in_process(plan)
            return
        except BaseException:
            # Interrupt: cancel the queued bodies before waiting for anything,
            # so a Ctrl-C does not have to drain the rest of the tree.
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)
        for plan, outcome in zip(plans, outcomes, strict=True):
            self.outcomes[plan.key] = outcome
            self._save_cached(plan, outcome)

    def _parse_in_process(self, plan: Plan) -> ParseOutcome:
        """Parse one plan through the executor's own cache, parser, and errors."""
        artifact = plan.artifact
        program_name = plan.declared_by if plan.declared_by is not None else plan.name
        dependency = None if plan.declared_by is None else plan.name
        try:
            ast = self._load_ast(artifact.code_path, program_name=program_name, dependency=dependency)
        except ProjectLoadError as exc:
            # ``_load_ast`` wraps the parser exception in a load error for its
            # other callers. Keep the parser exception itself as the cause, so
            # the in-process and worker paths expose the same chain.
            return ParseOutcome(failure=str(exc), error=exc.__cause__ or exc)
        return ParseOutcome(ast=ast)

    def _save_cached(self, plan: Plan, outcome: ParseOutcome) -> None:
        """Store a body the worker parsed and did not cache itself.

        A worker never writes the cache, so the per-user key and the entry
        signatures stay single-process. A parse that came from the cache has
        nothing to store, and a body whose source changed while the worker was
        reading it is left uncached rather than stored under newer metadata.
        """
        if outcome.ast is None or outcome.cached or self._ast_cache is None:
            return
        code_path = plan.artifact.code_path
        try:
            self._ast_cache.save(code_path, self._mode.value, outcome.ast, snapshot=outcome.snapshot)
        except OSError as exc:
            # The cache is an optimisation: a failed write must not turn a
            # successful parse into a load failure.
            self._dbg(f"Cache write failed for {code_path}: {exc}")

    def _load_ast(self, code_path: Path, *, program_name: str, dependency: str | None) -> BasePicture:
        if self._ast_cache is not None:
            cached = self._ast_cache.load(code_path, self._mode.value)
            if cached is not None:
                self._dbg(f"Using cached AST for: {code_path}")
                return cached
        # Read the source once and hash those bytes: the entry written below then
        # describes exactly the revision that was parsed, never a later stat.
        try:
            raw_bytes = code_path.read_bytes()
        except OSError as exc:
            if dependency is None:
                raise ArtifactLoadError(program_name, f"unable to read {code_path.name}") from exc
            raise DependencyParseError(
                program_name,
                f"unable to read dependency {dependency!r}",
                dependency=dependency,
            ) from exc
        snapshot = source_snapshot(code_path, raw_bytes)
        self._dbg(f"Parsing: {code_path}")
        try:
            basepicture = parse_source_bytes(
                raw_bytes,
                source_path=code_path,
                debug=self._debug,
                log_failures=self._log_failures,
            )
        except PARSE_FAILURES as exc:
            if dependency is None:
                raise ArtifactLoadError(program_name, f"failed to parse {code_path.name}") from exc
            raise DependencyParseError(
                program_name,
                f"failed to parse dependency {dependency!r}",
                dependency=dependency,
            ) from exc
        if self._ast_cache is not None:
            try:
                self._ast_cache.save(code_path, self._mode.value, basepicture, snapshot=snapshot)
            except OSError as exc:
                # The cache is an optimisation: a failed write must not turn a
                # successful parse into a load failure.
                self._dbg(f"Cache write failed for {code_path}: {exc}")
        return basepicture
