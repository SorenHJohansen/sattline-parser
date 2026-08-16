"""Standalone fuzz harness for SattLine parser.

Provides hard-timeout parsing, crash capture, and corpus-seeded fuzzing for
parser entry points.

Timeouts are enforced with a dedicated worker subprocess that parses one input
at a time. The worker is reused across inputs (no process spawn per input), and
on timeout it is killed and replaced — Python threads cannot be killed safely,
so a real hard timeout requires a separate process.
"""

from __future__ import annotations

import json
import pathlib
import queue
import random
import struct
import subprocess
import sys
import threading
import time
import typing as t

from .models.ast_model import BasePicture

_WORKER_HEADER = struct.Struct(">I")

#: Worker entrypoint. Reads length-prefixed UTF-8 sources, parses each one and
#: writes back a length-prefixed JSON result. Run as ``python -c <this>`` so the
#: harness can enforce hard timeouts by killing the process.
_WORKER_SOURCE = r"""
import json
import struct
import sys
import time

from sattline_parser.api import parse_source_text

_HEADER = struct.Struct(">I")


def _write(payload: bytes) -> None:
    sys.stdout.buffer.write(_HEADER.pack(len(payload)) + payload)
    sys.stdout.buffer.flush()


def main() -> None:
    stdin = sys.stdin.buffer
    while True:
        header = stdin.read(_HEADER.size)
        if not header:
            return
        (length,) = _HEADER.unpack(header)
        data = stdin.read(length)
        if len(data) != length:
            return
        source = data.decode("utf-8", errors="replace")
        start = time.perf_counter()
        try:
            parse_source_text(source, log_failures=False)
            result: dict[str, object] = {"ok": True}
        except Exception as exc:  # noqa: BLE001 - serialised for the parent
            result = {
                "ok": False,
                "error_class": f"{type(exc).__module__}.{type(exc).__name__}",
                "error_message": str(exc)[:2000],
            }
        result["duration_ms"] = (time.perf_counter() - start) * 1000
        _write(json.dumps(result).encode("utf-8"))


if __name__ == "__main__":
    main()
"""


def _repo_root_from(anchor: pathlib.Path) -> pathlib.Path:
    current = anchor.resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / "pyproject.toml").is_file() and (current / "AGENTS.md").is_file():
            return current
        if current.parent == current:
            raise RuntimeError(f"Could not locate repository root from {anchor}")
        current = current.parent


def _optional_repo_root_from(anchor: pathlib.Path) -> pathlib.Path | None:
    try:
        return _repo_root_from(anchor)
    except RuntimeError:
        return None


REPO_ROOT = _optional_repo_root_from(pathlib.Path(__file__))
CORPUS_DIR = None if REPO_ROOT is None else REPO_ROOT / "tests" / "fixtures" / "corpus"
DEFAULT_TIMEOUT_SECONDS = 10


class FuzzResult:
    __slots__ = ("duration_ms", "error", "input_desc", "result", "success")

    def __init__(
        self,
        input_desc: str,
        *,
        success: bool,
        result: BasePicture | None = None,
        error: Exception | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        self.input_desc = input_desc
        self.success = success
        self.result = result
        self.error = error
        self.duration_ms = duration_ms

    def to_dict(self) -> dict[str, t.Any]:
        return {
            "input_desc": self.input_desc,
            "success": self.success,
            "result_type": type(self.result).__name__ if self.result else None,
            "error_type": type(self.error).__name__ if self.error else None,
            "error_message": str(self.error) if self.error else None,
            "duration_ms": self.duration_ms,
        }


class TimeoutError(Exception):
    pass


def _drain_worker_results(stream: t.IO[bytes], results_queue: queue.Queue[dict[str, object]]) -> None:
    """Read length-prefixed results from the worker *stream* until EOF/error."""
    try:
        while True:
            header = stream.read(_WORKER_HEADER.size)
            if not header:
                return
            (length,) = _WORKER_HEADER.unpack(header)
            payload = stream.read(length)
            if not payload:
                return
            results_queue.put(json.loads(payload.decode("utf-8")))
    except (OSError, ValueError, EOFError):
        return


class _FuzzWorker:
    """A reusable worker subprocess that parses one input at a time.

    Reading happens on a daemon thread so the caller can enforce a hard timeout
    via ``queue.get(timeout=...)``; a timed-out worker is killed and replaced.
    """

    def __init__(self, worker_source: str | None = None) -> None:
        # Read from the module attribute at call time so tests can monkeypatch it.
        self._worker_source = _WORKER_SOURCE if worker_source is None else worker_source
        self._proc: subprocess.Popen[bytes] | None = None
        self._results: queue.Queue[dict[str, object]] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()
        self._spawn()

    def _spawn(self) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, "-c", self._worker_source],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:  # pragma: no cover - defensive guard
            return
        _drain_worker_results(proc.stdout, self._results)

    def parse(self, source: str, timeout: float) -> dict[str, object]:
        """Parse *source* in the worker, enforcing a hard *timeout*."""
        proc = self._proc
        if proc is None or proc.stdin is None:
            self._restart()
            proc = self._proc
        if proc is None or proc.stdin is None:  # pragma: no cover - spawn always succeeds or raises
            return {"ok": False, "error_class": "WorkerError", "error_message": "worker failed to spawn"}
        try:
            data = source.encode("utf-8")
            proc.stdin.write(_WORKER_HEADER.pack(len(data)) + data)
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self._restart()
            return {"ok": False, "error_class": "WorkerError", "error_message": "worker process died"}
        try:
            return self._results.get(timeout=timeout)
        except queue.Empty:
            self._restart()
            return {
                "ok": False,
                "error_class": f"{__name__}.TimeoutError",
                "error_message": f"Parse timed out after {timeout}s",
                "duration_ms": timeout * 1000,
            }

    def _restart(self) -> None:
        with self._lock:
            self._close()
            self._drain_results()
            self._spawn()

    def _drain_results(self) -> None:
        while True:
            try:
                self._results.get_nowait()
            except queue.Empty:
                return

    def _close(self) -> None:
        import contextlib  # noqa: PLC0415

        proc = self._proc
        self._proc = None
        if proc is not None:
            with contextlib.suppress(OSError):  # pragma: no cover - defensive cleanup
                proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):  # pragma: no cover - SIGKILL always reaps
                proc.wait(timeout=1)
        if self._reader is not None and self._reader.is_alive():
            self._reader.join(timeout=1)  # pragma: no cover - timing dependent

    def close(self) -> None:
        with self._lock:
            self._close()


def _reconstruct_error(error_class: str, message: str) -> Exception:
    """Recreate an exception from its ``module.Class`` path and message.

    Real exception constructors (e.g. Lark's ``UnexpectedToken``) have
    non-trivial signatures, so a shim subclass whose ``__init__`` only calls
    ``Exception.__init__`` is used. ``isinstance`` checks against the original
    class therefore still pass while the message is preserved.
    """
    if not error_class or "." not in error_class:
        return RuntimeError(message or error_class or "fuzz failure")
    module_name, _, class_name = error_class.rpartition(".")
    try:
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name)

        def _message_only_init(self: Exception, msg: str) -> None:
            Exception.__init__(self, msg)

        if isinstance(cls, type) and issubclass(cls, BaseException):
            shim = type(
                f"Reconstructed{class_name}",
                (cls,),
                {"__init__": _message_only_init, "__str__": Exception.__str__},
            )
            return t.cast(Exception, shim(message))
    except (ImportError, AttributeError, TypeError):
        pass
    return RuntimeError(message or error_class)


def _as_float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _run_with_timeout(
    source: str,
    timeout: float,
) -> tuple[BasePicture | None, Exception | None, float]:
    start = time.perf_counter()
    worker = _FuzzWorker()
    try:
        raw = worker.parse(source, timeout)
    finally:
        worker.close()
    error: Exception | None = None
    result: BasePicture | None = None
    if not bool(raw.get("ok")):
        error = _reconstruct_error(str(raw.get("error_class") or ""), str(raw.get("error_message") or ""))
    duration = _as_float(raw.get("duration_ms", (time.perf_counter() - start) * 1000))
    return result, error, duration


def fuzz_parse_text(
    source: str,
    input_desc: str | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> FuzzResult:
    if input_desc is None:
        input_desc = f"text({len(source)} chars)"
    result, error, duration_ms = _run_with_timeout(source, timeout)
    return FuzzResult(
        input_desc=input_desc,
        success=error is None,
        result=result if isinstance(result, BasePicture) else None,
        error=error,
        duration_ms=duration_ms,
    )


def collect_corpus_inputs(
    corpus_dir: pathlib.Path | None = None,
    *,
    include_valid: bool = True,
    include_invalid: bool = True,
    include_edge_cases: bool = True,
    include_semantic: bool = False,
    max_files: int | None = None,
) -> list[tuple[str, str]]:
    if corpus_dir is None:
        if CORPUS_DIR is None:
            return []
        corpus_dir = CORPUS_DIR
    subdirs: list[pathlib.Path] = []
    if include_valid:
        subdirs.append(corpus_dir / "valid")
    if include_invalid:
        subdirs.append(corpus_dir / "invalid")
    if include_edge_cases:
        subdirs.append(corpus_dir / "edge_cases")
    if include_semantic:
        subdirs.append(corpus_dir / "semantic")

    inputs: list[tuple[str, str]] = []
    for subdir in subdirs:
        if not subdir.exists():
            continue
        files: list[pathlib.Path] = sorted(subdir.glob("*.s"))
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                inputs.append((str(file_path), content))
            except OSError:
                continue
    if max_files is not None:
        inputs = inputs[:max_files]
    return inputs


def run_corpus_regression(
    corpus_dir: pathlib.Path | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_files: int | None = None,
) -> list[FuzzResult]:
    inputs = collect_corpus_inputs(corpus_dir, max_files=max_files)
    results: list[FuzzResult] = []
    worker = _FuzzWorker()
    try:
        for file_path, content in inputs:
            desc = pathlib.Path(file_path).name
            raw = worker.parse(content, timeout)
            error = (
                None
                if raw.get("ok")
                else _reconstruct_error(str(raw.get("error_class") or ""), str(raw.get("error_message") or ""))
            )
            results.append(
                FuzzResult(
                    input_desc=f"corpus:{desc}",
                    success=bool(raw.get("ok")),
                    error=error,
                    duration_ms=_as_float(raw.get("duration_ms", 0.0)),
                )
            )
    finally:
        worker.close()
    return results


def generate_random_text(
    length: int = 100,
    *,
    seed: int | None = None,
) -> str:
    rng = random.Random(seed) if seed is not None else random  # nosec B311
    tokens = [
        "PROGRAM",
        "ENDPROGRAM",
        "ModuleTypeDef",
        "SubModule",
        "EndModuletype",
        "SingleModule",
        "EndModule",
        "EQUATION:",
        "ENDEQUATION",
        "SEQUENCE:",
        "ENDSEQUENCE",
        "Step",
        "Transition",
        "VAR",
        "END_VAR",
        ":=",
        ";",
        ",",
        "(",
        ")",
        ".",
        "TRUE",
        "FALSE",
        "AND",
        "OR",
        "NOT",
        "IF",
        "THEN",
        "ELSE",
        "END_IF",
        "123",
        "3.14",
        "'hello'",
        '"world"',
        "x",
        "y",
        "z",
        "Result",
        "State",
        "\n",
        " ",
        "\t",
    ]
    result: list[str] = []
    current_length = 0
    while current_length < length:
        remaining_length = length - current_length
        fitting_tokens = [token for token in tokens if len(token) <= remaining_length]
        if not fitting_tokens:
            break
        # Fuzz harness intentionally uses non-cryptographic randomness.
        token = rng.choice(fitting_tokens)  # nosec B311
        result.append(token)
        current_length += len(token)
    return "".join(result)


def run_random_fuzz(
    rounds: int = 100,
    *,
    text_length: int = 100,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    seed: int | None = None,
) -> list[FuzzResult]:
    if seed is not None:
        random.seed(seed)
    results: list[FuzzResult] = []
    worker = _FuzzWorker()
    try:
        for i in range(rounds):
            source = generate_random_text(text_length, seed=seed + i if seed else None)
            raw = worker.parse(source, timeout)
            error = (
                None
                if raw.get("ok")
                else _reconstruct_error(str(raw.get("error_class") or ""), str(raw.get("error_message") or ""))
            )
            results.append(
                FuzzResult(
                    input_desc=f"random:{i}({text_length} chars)",
                    success=bool(raw.get("ok")),
                    error=error,
                    duration_ms=_as_float(raw.get("duration_ms", 0.0)),
                )
            )
    finally:
        worker.close()
    return results


def assert_no_crashes(results: list[FuzzResult]) -> None:
    crashes = [r for r in results if r.error and not _is_expected_parse_error(r.error)]
    if crashes:
        messages = "\n".join(f"  - {r.input_desc}: {type(r.error).__name__}: {r.error}" for r in crashes[:5])
        raise AssertionError(f"{len(crashes)} crash(es) detected:\n{messages}")


def assert_no_timeouts(results: list[FuzzResult]) -> None:
    timeouts = [r for r in results if isinstance(r.error, TimeoutError)]
    if timeouts:
        messages = "\n".join(f"  - {r.input_desc}: {r.duration_ms:.1f}ms" for r in timeouts[:5])
        raise AssertionError(f"{len(timeouts)} timeout(s) detected:\n{messages}")


def _is_expected_parse_error(error: Exception) -> bool:
    """True only for *expected* invalid-input errors.

    Broad built-in exceptions such as ``ValueError``/``SyntaxError`` are NOT
    considered expected: an internal transformer or parser bug raising one must
    be treated as a fuzz failure.
    """
    from lark.exceptions import UnexpectedInput  # noqa: PLC0415

    from sattline_parser.preprocessing import PreprocessError  # noqa: PLC0415

    return isinstance(error, UnexpectedInput | PreprocessError)


def is_expected_parse_error(error: Exception) -> bool:
    return _is_expected_parse_error(error)
