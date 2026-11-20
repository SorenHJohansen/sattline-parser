# pyright: reportPrivateUsage=false
"""Unit tests for recursive program loading (``project/loader.py``)."""

from __future__ import annotations

import logging
import os
import pickle
from collections.abc import Callable, Generator, Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import NoReturn
from unittest.mock import patch

import pytest
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, VisitError

from sattline_parser.api import parse_source_bytes, parse_source_file
from sattline_parser.cli.cmds.project import _discover_targets
from sattline_parser.errors import SourceTooDeepError
from sattline_parser.models.ast_model import (
    BasePicture,
)
from sattline_parser.preprocessing.compressed import PreprocessError
from sattline_parser.project import (
    ArtifactIdentity,
    ArtifactLoadError,
    DependencyCycleError,
    DependencyNotFoundError,
    DependencyParseError,
    LoadMode,
    ProjectLoadError,
    SattLineProject,
    StructuralProjectError,
    read_dependency_names,
)
from sattline_parser.project import executor as executor_module
from sattline_parser.project import loader as project_loader
from sattline_parser.project import parallel as project_loader_parallel
from sattline_parser.project import plan as plan_module
from sattline_parser.project.assembler import ProjectAssembler
from sattline_parser.project.ast_cache import FileASTCache, SourceSnapshot, source_snapshot
from sattline_parser.project.executor import (
    MAX_FAILURE_SOURCE_LINE,
    MAX_UNICODE_ERROR_BYTES,
    MAX_WORKER_DEBUG_MESSAGES,
    ParseFailure,
    parse_code_file,
    rebuild_parse_failure,
)
from sattline_parser.project.formats import CompanionIndex
from sattline_parser.project.models import LoadDiagnosticKind, SidecarState
from sattline_parser.project.parallel import load_in_progress, loads_in_progress, pool_allowed, start_method
from sattline_parser.project.planner import ProjectPlanner
from sattline_parser.transformer.sl_transformer import SLTransformer

from ._support import write_file

_CODE = """"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: Prog"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""

_BROKEN = "this is not a SattLine program at all $$$"

#: ``_CODE`` with two ``Layer_`` arguments in its module header. The transformer
#: rejects the second one as a duplicate singular clause.
_DUPLICATE_CLAUSE_CODE = _CODE.replace(
    "1.0 , 1.0\n    ) : MODULEDEFINITION",
    "1.0 , 1.0 Layer_ = 1 Layer_ = 2\n    ) : MODULEDEFINITION",
)

_GFX = """" Syntax version 2.23, date: 2026-06-19-12:41:09.218 N "

 5
 None  True  -2.40000E-01 1.08000E+00
  1.38000E+00 1.28000E+00
 0
 2
 Var 0 12 OprPathIndex  Lit 0 2 -1     2
1 1 Var  Invalid  6 PathOK
2 1 Var  Invalid  9 PathNotOK
 0
 None  True
t
           0
"""

_GFX_UNTERMINATED = " 4\n some\n none\n"


def _load(
    root: Path,
    *,
    targets: tuple[str, ...] = ("Main",),
    mode: LoadMode = LoadMode.DRAFT,
    cache_dir: Path | None = None,
    debug: list[str] | None = None,
    workers: int = 1,
) -> SattLineProject:
    def _debug(message: str) -> None:
        assert debug is not None
        debug.append(message)

    return SattLineProject.load(
        roots=[root],
        mode=mode,
        targets=targets,
        debug=_debug if debug is not None else None,
        cache_dir=cache_dir,
        workers=workers,
    )


_Task = tuple[str, str, str | None]


class _RecordingPool:
    """Wraps a real pool and records the tasks the parent dispatches to it."""

    def __init__(self, pool: ProcessPoolExecutor, seen: list[str]) -> None:
        self._pool = pool
        self._seen = seen

    def __enter__(self) -> _RecordingPool:
        self._pool.__enter__()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> object:
        return self._pool.__exit__(exc_type, exc_val, exc_tb)  # pyright: ignore[reportArgumentType]

    def map(self, function: Callable[[_Task], object], iterable: list[_Task], chunksize: int = 1) -> Iterator[object]:
        for task in iterable:
            self._seen.append(task[0])
        return self._pool.map(function, iterable, chunksize=chunksize)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=cancel_futures)


def _record_dispatched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch the pool factory so the parent records every dispatched body."""
    real_factory = project_loader_parallel.process_pool
    seen: list[str] = []

    def factory(max_workers: int) -> _RecordingPool:
        return _RecordingPool(real_factory(max_workers), seen)

    monkeypatch.setattr(project_loader_parallel, "process_pool", factory)
    return seen


def _counting_parse(call_count: list[int]) -> Callable[..., BasePicture]:
    def counting_parse(raw_bytes: bytes, **_: object) -> BasePicture:
        call_count.append(1)
        return parse_source_bytes(raw_bytes)

    return counting_parse


def test_read_dependency_names_trim_and_ignore_blanks(tmp_path: Path) -> None:
    deps = tmp_path / "Main.l"
    deps.write_text("  Lib1  \n\n Lib2\t\n\n\n  \nLib3\n", encoding="utf-8")
    assert read_dependency_names(deps) == ("Lib1", "Lib2", "Lib3")


def test_load_resolves_single_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    project = _load(tmp_path)
    program = project.get("Main")
    assert program.name == "Main"
    assert isinstance(program.code, BasePicture)
    assert program.dependencies == ()
    assert program.graphics is None
    assert program.format.mode is LoadMode.DRAFT
    assert program.format.code_ext == ".s"
    assert program.format.deps_ext is None
    assert program.source_path == (tmp_path / "Main.s").resolve()
    assert tuple(project.programs()) == ("main",)


def test_load_resolves_multiple_targets(tmp_path: Path) -> None:
    write_file(tmp_path, "A.s", _CODE)
    write_file(tmp_path, "B.s", _CODE)
    project = _load(tmp_path, targets=("A", "B"))
    assert ("a" in project) and ("b" in project)
    assert len(project.programs()) == 2


def test_load_recursive_dependencies(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib1\nLib2\n")
    write_file(tmp_path, "Lib1.s", _CODE)
    write_file(tmp_path, "Lib1.l", "Lib2\n")
    write_file(tmp_path, "Lib2.s", _CODE)
    project = _load(tmp_path)
    assert project.dependencies_of("Main") == ("Lib1", "Lib2")
    assert project.dependencies_of("Lib1") == ("Lib2",)
    assert project.dependencies_of("Lib2") == ()
    assert set(project.programs()) == {"main", "lib1", "lib2"}


def test_load_diamond_dependency_loads_once(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "A\nB\n")
    write_file(tmp_path, "A.s", _CODE)
    write_file(tmp_path, "A.l", "C\n")
    write_file(tmp_path, "B.s", _CODE)
    write_file(tmp_path, "B.l", "C\n")
    write_file(tmp_path, "C.s", _CODE)
    project = _load(tmp_path)
    assert len(project.programs()) == 4
    # Dependents are spelled the way each dependent declares itself, matching
    # ``dependencies_of``.
    assert project.dependents_of("C") == ("A", "B")
    assert project.graph().nodes == ("a", "b", "c", "main")


def test_load_duplicate_dependency_loads_once(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\nLib\n")
    write_file(tmp_path, "Lib.s", _CODE)
    project = _load(tmp_path)
    assert len(project.programs()) == 2
    assert project.dependencies_of("Main") == ("Lib", "Lib")
    assert project.graph().edges.count(("main", "lib")) == 2


def test_load_cycle_is_an_error_not_an_edge(tmp_path: Path) -> None:
    write_file(tmp_path, "A.s", _CODE)
    write_file(tmp_path, "A.l", "B\n")
    write_file(tmp_path, "B.s", _CODE)
    write_file(tmp_path, "B.l", "A\n")
    with pytest.raises(DependencyCycleError):
        _load(tmp_path, targets=("A",))


def test_load_targets_canonicalized_by_case(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    project = _load(tmp_path, targets=("Main", "MAIN"))
    assert len(project.programs()) == 1
    assert project.get("mAiN").name == "Main"


def test_load_resolves_dependencies_through_the_path_order(tmp_path: Path) -> None:
    """A dependency resolves through the same path, not beside its consumer."""
    consumer = tmp_path / "consumer"
    library = tmp_path / "library"
    write_file(consumer, "Client.s", _CODE)
    write_file(consumer, "Client.l", "LibA\n")
    write_file(library, "LibA.s", _CODE)
    write_file(library, "LibA.l", "LibB\n")
    write_file(consumer, "LibB.s", _CODE)
    write_file(consumer, "LibB.l", "ConsumerSide\n")
    write_file(library, "LibB.s", _CODE)
    write_file(library, "LibB.l", "LibrarySide\n")
    write_file(consumer, "ConsumerSide.s", _CODE)
    write_file(library, "LibrarySide.s", _CODE)

    project = SattLineProject.load([consumer, library], LoadMode.DRAFT, ["Client"])

    assert project.get("LibB").resolved_base == consumer.resolve()
    assert project.dependencies_of("LibA") == ("LibB",)
    assert project.dependencies_of("LibB") == ("ConsumerSide",)


def test_load_dependency_path_order_follows_the_reversed_roots(tmp_path: Path) -> None:
    """With the library first, the same names resolve to the library's bodies."""
    consumer = tmp_path / "consumer"
    library = tmp_path / "library"
    write_file(consumer, "Client.s", _CODE)
    write_file(consumer, "Client.l", "LibA\n")
    write_file(library, "LibA.s", _CODE)
    write_file(library, "LibA.l", "LibB\n")
    write_file(consumer, "LibB.s", _CODE)
    write_file(consumer, "LibB.l", "ConsumerSide\n")
    write_file(library, "LibB.s", _CODE)
    write_file(library, "LibB.l", "LibrarySide\n")
    write_file(consumer, "ConsumerSide.s", _CODE)
    write_file(library, "LibrarySide.s", _CODE)

    project = SattLineProject.load([library, consumer], LoadMode.DRAFT, ["Client"])

    assert project.get("LibB").resolved_base == library.resolve()
    assert project.dependencies_of("LibB") == ("LibrarySide",)


def test_load_missing_dependency_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Ghost\n")
    with pytest.raises(DependencyNotFoundError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Ghost"


def test_load_missing_target_raises_without_dependency(tmp_path: Path) -> None:
    write_file(tmp_path, "Other.s", _CODE)
    with pytest.raises(DependencyNotFoundError) as exc_info:
        _load(tmp_path, targets=("Ghost",))
    assert exc_info.value.program == "Ghost"
    assert exc_info.value.dependency is None


def test_load_target_parse_failure_raises_artifact_error(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _BROKEN)
    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency is None


def test_load_dependency_parse_failure_raises_dependency_error(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Broken\n")
    write_file(tmp_path, "Broken.s", _BROKEN)
    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Broken"


def test_worker_and_in_process_failures_have_the_same_cause(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Broken\n")
    write_file(tmp_path, "Broken.s", _BROKEN)

    causes: dict[int, BaseException] = {}
    artifacts: dict[int, tuple[Path | None, str | None]] = {}
    for workers in (1, 2):
        with pytest.raises(DependencyParseError) as exc_info:
            _load(tmp_path, workers=workers)
        cause = exc_info.value.__cause__
        assert cause is not None
        causes[workers] = cause
        artifacts[workers] = (exc_info.value.path, exc_info.value.source_line)

    assert artifacts[1] == (tmp_path / "Broken.s", _BROKEN.rstrip("\n"))
    assert artifacts[2] == (tmp_path / "Broken.s", _BROKEN.rstrip("\n"))

    in_process = causes[1]
    worker = causes[2]
    assert type(worker) is type(in_process)
    assert isinstance(in_process, UnexpectedInput)
    assert isinstance(worker, UnexpectedInput)
    assert worker.line == in_process.line
    assert worker.column == in_process.column


@pytest.mark.parametrize(
    ("type_name", "expected_type"),
    [
        ("UnexpectedCharacters", UnexpectedCharacters),
        ("UnexpectedEOF", UnexpectedEOF),
        ("UnexpectedInput", UnexpectedInput),
        ("PreprocessError", PreprocessError),
        ("UnicodeDecodeError", UnicodeError),
        ("UnicodeError", UnicodeError),
        ("ValueError", ValueError),
        ("OSError", OSError),
        ("PermissionError", PermissionError),
        ("FileNotFoundError", FileNotFoundError),
        ("IsADirectoryError", IsADirectoryError),
        ("NotADirectoryError", NotADirectoryError),
        ("FileExistsError", FileExistsError),
        ("TimeoutError", TimeoutError),
        ("RuntimeError", RuntimeError),
    ],
)
def test_rebuild_parse_failure_keeps_the_worker_type(type_name: str, expected_type: type[BaseException]) -> None:
    record = ParseFailure(
        type_name=type_name,
        message="boom",
        line=4,
        column=7,
        pos_in_stream=11,
    )

    rebuilt = rebuild_parse_failure(record)

    assert type(rebuilt) is expected_type


def test_rebuild_parse_failure_keeps_the_source_depth_limit() -> None:
    record = ParseFailure(
        type_name="SourceTooDeepError",
        message="too deep",
        line=4,
        column=7,
        pos_in_stream=11,
        limit=200,
    )

    rebuilt = rebuild_parse_failure(record)

    assert isinstance(rebuilt, SourceTooDeepError)
    assert rebuilt.limit == 200
    assert (rebuilt.line, rebuilt.column, rebuilt.pos_in_stream) == (4, 7, 11)


def test_rebuild_parse_failure_keeps_a_decode_error() -> None:
    record = ParseFailure(
        type_name="UnicodeDecodeError",
        message="bad byte",
        unicode_error=("utf-8", b"\xff", 0, 1, "invalid start byte"),
    )

    rebuilt = rebuild_parse_failure(record)

    assert isinstance(rebuilt, UnicodeDecodeError)
    assert rebuilt.start == 0
    assert rebuilt.reason == "invalid start byte"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")
@pytest.mark.parametrize("workers", [1, 2])
def test_load_unreadable_body_is_a_project_error(tmp_path: Path, workers: int) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.s").chmod(0)

    with pytest.raises(ArtifactLoadError):
        _load(tmp_path, workers=workers)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")
def test_load_unreadable_body_in_a_worker_is_a_project_error(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Lib.s", _CODE)
    (tmp_path / "Main.s").chmod(0)

    with pytest.raises(ArtifactLoadError):
        _load(tmp_path, targets=("Main", "Lib"), workers=2)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")
def test_a_worker_read_error_keeps_its_oserror_subclass_as_the_cause(tmp_path: Path) -> None:
    """The parent must not rebuild a PermissionError as a plain RuntimeError."""
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Broken\n")
    write_file(tmp_path, "Broken.s", _CODE)
    (tmp_path / "Broken.s").chmod(0)

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path, workers=2)

    assert isinstance(exc_info.value.__cause__, PermissionError)


def test_a_transformer_rejection_fails_a_project_load_as_a_parse_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected duplicate clause is a parse failure, not an internal error."""
    write_file(tmp_path, "Main.s", _DUPLICATE_CLAUSE_CODE)

    def reject(self: SLTransformer, items: list[object]) -> NoReturn:
        raise ValueError("module header has more than one Layer_ argument")

    monkeypatch.setattr(SLTransformer, "argument", reject)

    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)

    cause = exc_info.value.__cause__
    assert isinstance(cause, ValueError)
    assert isinstance(cause.__cause__, VisitError)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")
def test_parse_code_file_reports_an_unreadable_body(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    code_path = tmp_path / "Main.s"
    code_path.chmod(0)

    outcome = parse_code_file((str(code_path), "draft", None, False, False))

    assert outcome.ast is None
    assert outcome.failure_record is not None
    assert outcome.failure_record.type_name == "PermissionError"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")
def test_load_unreadable_dependency_body_is_a_dependency_error(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Broken\n")
    write_file(tmp_path, "Broken.s", _CODE)
    (tmp_path / "Broken.s").chmod(0)

    with pytest.raises(DependencyParseError):
        _load(tmp_path)


def test_a_directory_named_like_a_deps_file_is_not_a_sidecar(tmp_path: Path) -> None:
    """Only a regular file pairs; a directory at the sidecar prefix is absent."""
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").mkdir(exist_ok=True)

    project = _load(tmp_path)

    program = project.get("Main")
    assert program.deps_path is None
    assert program.sidecar is SidecarState.ABSENT
    assert [d.kind for d in project.diagnostics()] == [LoadDiagnosticKind.SIDECAR_MISSING]


def test_load_draft_fallback_extensions(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.z", "Lib\n")
    write_file(tmp_path, "Lib.x", _CODE)
    project = _load(tmp_path)
    assert project.get("Main").format.code_ext == ".x"
    assert project.get("Main").format.deps_ext == ".z"
    # The resolved body's suffix decides the artifact family, so a draft load
    # that fell back to an official body reports the official family.
    assert project.get("Main").format.mode is LoadMode.OFFICIAL


def test_load_arbitrary_graphics_companion_does_not_raise(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.g", "GRAPHICS")
    project = _load(tmp_path)
    program = project.programs()["main"]
    assert program.graphics is not None
    assert program.graphics.messages == ()


def test_load_empty_targets(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    project = _load(tmp_path, targets=())
    assert len(project.programs()) == 0


def test_load_debug_callback(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    debug: list[str] = []
    _load(tmp_path, debug=debug)
    assert any("Visiting: Main" in line for line in debug)
    assert any("Parsing:" in line for line in debug)


@contextmanager
def _spy_on_parse(call_count: list[int]) -> Generator[None]:
    with patch.object(executor_module, "parse_source_bytes", side_effect=_counting_parse(call_count)):
        yield


def test_load_ast_cache_reuses_parsed_programs(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")
    write_file(tmp_path, "Lib.s", _CODE)
    cache_dir = tmp_path / "cache"
    call_count: list[int] = []
    with _spy_on_parse(call_count):
        first = _load(tmp_path, cache_dir=cache_dir)
        parsed_on_first_load = len(call_count)
        call_count.clear()
        second = _load(tmp_path, cache_dir=cache_dir)
        parsed_on_second_load = len(call_count)

    assert "main" in first and "lib" in first
    assert "main" in second and "lib" in second
    assert parsed_on_first_load == 2
    assert parsed_on_second_load == 0
    assert (cache_dir / "file_lookup_cache.json").exists()


def test_load_without_cache_dir_reparses(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    call_count: list[int] = []
    with _spy_on_parse(call_count):
        _load(tmp_path)
        first = len(call_count)
        _load(tmp_path)
        second = len(call_count)

    assert first == 1
    assert second == 2


def test_load_fails_closed_when_the_cache_root_is_foreign(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr("sattline_parser.source_io._IS_WINDOWS", False)
    monkeypatch.setattr("sattline_parser.source_io._getuid", lambda: -1)

    project = _load(tmp_path, cache_dir=cache_dir)

    assert "main" in project
    assert not (cache_dir / "file_lookup_cache.json").exists()
    assert not (cache_dir / "file_ast").exists()


def test_load_ast_cache_reparses_after_source_change(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    cache_dir = tmp_path / "cache"
    call_count: list[int] = []
    with _spy_on_parse(call_count):
        first = _load(tmp_path, cache_dir=cache_dir)
        assert len(call_count) == 1
        write_file(tmp_path, "Main.s", _CODE + "\n")
        second = _load(tmp_path, cache_dir=cache_dir)

    assert "main" in first and "main" in second
    assert len(call_count) == 2


def test_load_reparses_a_same_size_edit_that_keeps_the_mtime(tmp_path: Path) -> None:
    """The cache identity is the source bytes, not the stat snapshot."""
    source = write_file(tmp_path, "Main.s", _CODE)
    cache_dir = tmp_path / "cache"
    call_count: list[int] = []
    with _spy_on_parse(call_count):
        _load(tmp_path, cache_dir=cache_dir)
        stat_result = source.stat()
        edited = _CODE.replace("name: Prog", "name: Proq")
        assert len(edited) == len(_CODE)
        source.write_text(edited, encoding="utf-8")
        os.utime(source, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns))
        _load(tmp_path, cache_dir=cache_dir)

    assert len(call_count) == 2


# --- Graphics companion wiring -------------------------------------------------


def test_load_parses_graphics_companion(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.g", _GFX)

    program = _load(tmp_path).programs()["main"]

    assert program.format.graphics_ext == ".g"
    assert program.graphics is not None
    assert program.graphics.messages == ()
    assert [(b.kind, b.raw_text) for b in program.graphics.bindings] == [
        ("var", "OprPathIndex"),
        ("lit", "-1"),
        ("var", "PathOK"),
        ("var", "PathNotOK"),
    ]


def test_load_draft_body_does_not_use_official_graphics(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.y", _GFX)

    program = _load(tmp_path).programs()["main"]

    assert program.format.graphics_ext is None
    assert program.graphics is None


def test_load_without_graphics_companion(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    program = _load(tmp_path).programs()["main"]

    assert program.format.graphics_ext is None
    assert program.graphics is None


def test_load_official_mode_ignores_draft_graphics(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.g", _GFX)

    program = _load(tmp_path, mode=LoadMode.OFFICIAL).programs()["main"]

    assert program.format.graphics_ext is None
    assert program.graphics is None


def test_load_official_mode_uses_official_graphics(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.y", _GFX)

    program = _load(tmp_path, mode=LoadMode.OFFICIAL).programs()["main"]

    assert program.format.graphics_ext == ".y"
    assert program.graphics is not None


def test_load_x_code_only_accepts_official_graphics(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.g", _GFX)
    write_file(tmp_path, "Main.y", _GFX)

    program = _load(tmp_path).programs()["main"]

    assert program.format.graphics_ext == ".y"
    assert program.graphics is not None


def test_a_directory_named_like_a_graphics_companion_is_not_a_companion(tmp_path: Path) -> None:
    """Only a regular file can be a companion; a directory is not one."""
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.g").mkdir()

    program = _load(tmp_path).programs()["main"]

    assert program.graphics is None
    assert program.format.graphics_ext is None


def test_a_directory_named_like_a_dependency_graphics_companion_is_not_a_companion(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.l", "Lib\n")
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Lib.s", _CODE)
    (tmp_path / "Lib.g").mkdir()

    project = _load(tmp_path)

    assert project.get("Lib").graphics is None


# --- distribution companion wiring ---------------------------------------------

_DISTRIBUTION = (
    "DistributionData\n"
    ' ( Version "Distributiondata version 1.0" )\n'
    "SourceCodeSystems\n"
    " (  )\n"
    "ExecutingSystems\n"
    " ( Controller\n"
    '    ( Name "172.18.0.1"\n'
    "      Download ShortStopReconfig ) )\n"
)

_DISTRIBUTION_EMPTY = (
    'DistributionData\n ( Version "Distributiondata version 1.0" )\nSourceCodeSystems\n (  )\nExecutingSystems\n (  )\n'
)


def test_load_parses_distribution_companion(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.p", _DISTRIBUTION)

    program = _load(tmp_path).programs()["main"]

    assert program.format.distribution_ext == ".p"
    assert program.distribution_path == tmp_path / "Main.p"
    assert program.has_executing_system is True
    assert program.distribution is not None
    assert [(t.kind, t.name, t.download) for t in program.distribution.executing_systems] == [
        ("Controller", "172.18.0.1", "ShortStopReconfig")
    ]


def test_load_empty_executing_systems_is_false(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.p", _DISTRIBUTION_EMPTY)

    program = _load(tmp_path).programs()["main"]

    assert program.has_executing_system is False


def test_load_without_distribution_companion_is_unknown(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    program = _load(tmp_path).programs()["main"]

    assert program.format.distribution_ext is None
    assert program.distribution_path is None
    assert program.distribution is None
    assert program.has_executing_system is None


def test_load_draft_body_does_not_use_official_distribution(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.q", _DISTRIBUTION)

    program = _load(tmp_path).programs()["main"]

    assert program.format.distribution_ext is None
    assert program.has_executing_system is None


def test_load_official_mode_ignores_draft_distribution(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.p", _DISTRIBUTION)

    program = _load(tmp_path, mode=LoadMode.OFFICIAL).programs()["main"]

    assert program.format.distribution_ext is None
    assert program.has_executing_system is None


def test_load_x_code_only_accepts_official_distribution(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.p", _DISTRIBUTION)
    write_file(tmp_path, "Main.q", _DISTRIBUTION)

    program = _load(tmp_path).programs()["main"]

    assert program.format.distribution_ext == ".q"


def test_load_distribution_decode_failure_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.p").write_bytes(b"\x81\n")

    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert exc_info.value.path == tmp_path / "Main.p"


def test_load_malformed_distribution_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.p", "not a distribution companion\n")

    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert "distribution companion" in str(exc_info.value)


def test_load_dependency_distribution_failure_raises_dependency_parse_error(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.l", "Lib\n")
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Lib.p", "not a distribution companion\n")

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Lib"


def test_load_distribution_is_read_even_with_a_warm_ast_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.p", _DISTRIBUTION_EMPTY)

    first = _load(tmp_path, cache_dir=cache_dir).programs()["main"]
    assert first.has_executing_system is False

    write_file(tmp_path, "Main.p", _DISTRIBUTION)
    second = _load(tmp_path, cache_dir=cache_dir).programs()["main"]

    assert second.has_executing_system is True


def test_load_distribution_companion_appearing_later_is_seen(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    write_file(tmp_path, "Main.s", _CODE)

    assert _load(tmp_path, cache_dir=cache_dir).programs()["main"].has_executing_system is None

    write_file(tmp_path, "Main.p", _DISTRIBUTION)
    assert _load(tmp_path, cache_dir=cache_dir).programs()["main"].has_executing_system is True


# --- artifact family coherence ------------------------------------------------

#: Each artifact family pairs only with itself: the body's suffix decides.
_FAMILY_CASES = [
    ("Main.s", "Main.l", "deps", ".l"),
    ("Main.x", "Main.z", "deps", ".z"),
    ("Main.s", "Main.g", "graphics", ".g"),
    ("Main.x", "Main.y", "graphics", ".y"),
    ("Main.s", "Main.p", "distribution", ".p"),
    ("Main.x", "Main.q", "distribution", ".q"),
]

_MISMATCH_CASES = [
    ("Main.s", "Main.z", "deps"),
    ("Main.x", "Main.l", "deps"),
    ("Main.s", "Main.y", "graphics"),
    ("Main.x", "Main.g", "graphics"),
    ("Main.s", "Main.q", "distribution"),
    ("Main.x", "Main.p", "distribution"),
]


def _companion_text(kind: str) -> str:
    if kind == "graphics":
        return _GFX
    if kind == "distribution":
        return _DISTRIBUTION
    return ""


@pytest.mark.parametrize(("body", "companion", "kind", "expected_ext"), _FAMILY_CASES)
def test_load_pairs_only_within_the_body_family(
    tmp_path: Path, body: str, companion: str, kind: str, expected_ext: str
) -> None:
    write_file(tmp_path, body, _CODE)
    write_file(tmp_path, companion, _companion_text(kind))

    program = _load(tmp_path).programs()["main"]

    resolved = getattr(program.format, f"{kind}_ext")
    assert resolved == expected_ext


@pytest.mark.parametrize(("body", "companion", "kind"), _MISMATCH_CASES)
def test_load_never_pairs_across_artifact_families(tmp_path: Path, body: str, companion: str, kind: str) -> None:
    write_file(tmp_path, body, _CODE)
    write_file(tmp_path, companion, _companion_text(kind))

    program = _load(tmp_path).programs()["main"]

    assert getattr(program.format, f"{kind}_ext") is None


def test_load_reports_a_same_directory_family_mismatch(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.z", "")

    project = _load(tmp_path)

    kinds = [d.kind for d in project.diagnostics()]
    assert LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH in kinds
    detail = next(d.detail for d in project.diagnostics() if d.kind is LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH)
    assert "does not match the artifact family" in detail


def test_load_official_body_with_draft_sidecar_is_not_paired(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.l", "")

    project = _load(tmp_path)

    assert project.get("Main").format.deps_ext is None
    assert LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH in [d.kind for d in project.diagnostics()]


def test_load_official_mode_reports_a_draft_sidecar_as_a_family_mismatch(tmp_path: Path) -> None:
    """The other family is probed at the body prefix, where a mode filter never looks."""
    write_file(tmp_path, "Main.x", _CODE)
    write_file(tmp_path, "Main.l", "")

    project = _load(tmp_path, mode=LoadMode.OFFICIAL)

    assert project.get("Main").format.deps_ext is None
    kinds = [d.kind for d in project.diagnostics()]
    assert LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH in kinds
    assert LoadDiagnosticKind.SIDECAR_MISSING not in kinds


def test_load_pairs_a_companion_whose_name_case_differs(tmp_path: Path) -> None:
    write_file(tmp_path, "PUMP.S", _CODE)
    (tmp_path / "pump.p").write_text(
        'DistributionData\n ( Version "Distributiondata version 1.0" )\n'
        "SourceCodeSystems\n (  )\n"
        'ExecutingSystems\n ( Controller\n    ( Name "10.0.0.1"\n      Download ShortStopReconfig ) )\n',
        encoding="utf-8",
    )

    project = _load(tmp_path, targets=("PUMP",))

    program = project.get("PUMP")
    assert program.distribution_path is not None
    # A case-insensitive filesystem may report the spelling it found on disk.
    assert program.distribution_path.name.lower() == "pump.p"
    assert program.has_executing_system is True


def test_parallel_parse_falls_back_when_the_pool_cannot_start_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Workers start on submit, so the failure surfaces from ``map``."""
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    class UnstartablePool:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def map(self, *args: object, **kwargs: object) -> object:
            raise OSError("cannot start a worker process")

        def shutdown(self, *args: object, **kwargs: object) -> None:
            pass

    def unstartable(max_workers: int) -> UnstartablePool:
        del max_workers
        return UnstartablePool()

    monkeypatch.setattr(project_loader_parallel, "process_pool", unstartable)
    project = _load(tmp_path, workers=2)

    assert tuple(project.programs()) == ("lib", "main")


# --- sidecar pairing invariant ----------------------------------------------


def test_load_dependency_sidecar_decode_failure_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").write_bytes(b"Lib \x81\n")

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency is None
    assert exc_info.value.path == tmp_path / "Main.l"


def test_load_graphics_decode_failure_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.g").write_bytes(b"\x81 graphics\n")

    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.path == tmp_path / "Main.g"


def test_load_dependency_graphics_decode_failure_raises_dependency_parse_error(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.l", "Lib\n")
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Lib.s", _CODE)
    (tmp_path / "Lib.g").write_bytes(b"\x81 graphics\n")

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Lib"


def test_load_survives_a_cache_write_failure(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    with patch.object(project_loader.FileASTCache, "save", side_effect=OSError("boom")):
        project = _load(tmp_path, cache_dir=tmp_path / "cache")

    assert "main" in project


def test_sidecar_is_not_paired_across_prefixes(tmp_path: Path) -> None:
    """A body must never be paired with a sidecar from another library prefix.

    ``consumer`` holds the body but no sidecar; ``other`` holds a sidecar only.
    The old whole-root lookup paired the two and then resolved that library's
    own dependencies relative to ``other``. The loader reads the sidecar at
    the selected body prefix and reports the failure instead, so the stray file
    becomes a diagnostic and no dependencies are invented.
    """
    consumer = tmp_path / "consumer"
    other = tmp_path / "other"
    write_file(consumer, "Main.s", _CODE)
    write_file(consumer, "Lib.s", _CODE)
    other.mkdir()
    write_file(other, "Lib.l", "OtherSide\n")
    write_file(other, "OtherSide.s", _CODE)

    project = SattLineProject.load([consumer, other], LoadMode.DRAFT, ["Main", "Lib"])

    program = project.get("Lib")
    assert program.dependencies == ()
    assert program.deps_path is None
    assert program.sidecar is SidecarState.ABSENT
    stray = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.SIDECAR_ELSEWHERE]
    assert [d.path for d in stray] == [other / "Lib.l"]


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="mode bits deny reads on POSIX, and root bypasses them",
)
def test_an_unreadable_root_is_a_project_load_error(tmp_path: Path) -> None:
    """A root that cannot be listed is an input problem, not an internal error."""
    write_file(tmp_path, "Main.s", _CODE)
    tmp_path.chmod(0o000)
    try:
        with pytest.raises(ProjectLoadError, match="cannot read"):
            _load(tmp_path)
    finally:
        tmp_path.chmod(0o755)


def test_missing_sidecar_is_reported_not_invented(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"])

    program = project.get("Main")
    assert program.dependencies == ()
    assert program.deps_path is None
    assert program.sidecar is SidecarState.ABSENT
    diagnostics = project.diagnostics()
    assert [d.kind for d in diagnostics] == [LoadDiagnosticKind.SIDECAR_MISSING]


def test_empty_sidecar_is_distinct_from_absent(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").write_text("\n\n", encoding="cp1252")

    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"])

    program = project.get("Main")
    assert program.sidecar is SidecarState.EMPTY
    assert program.dependencies == ()
    assert [d.kind for d in project.diagnostics()] == [LoadDiagnosticKind.SIDECAR_EMPTY]


def test_dependency_cycle_is_rejected_before_the_graph_is_returned(tmp_path: Path) -> None:
    write_file(tmp_path, "A.s", _CODE)
    write_file(tmp_path, "A.l", "B\n")
    write_file(tmp_path, "B.s", _CODE)
    write_file(tmp_path, "B.l", "A\n")

    with pytest.raises(DependencyCycleError) as excinfo:
        SattLineProject.load([tmp_path], LoadMode.DRAFT, ["A"])

    assert excinfo.value.cycle == ("a", "b", "a")


def test_a_cycle_through_an_alias_of_one_physical_body_is_rejected(tmp_path: Path) -> None:
    """Cycle detection follows resolved artifacts, not names.

    ``AliasLeft`` is another name for ``Left``'s body. The loop Left -> Right ->
    AliasLeft returns to the file that is already being planned, so it is a
    cycle even though no name repeats.
    """
    write_file(tmp_path, "Left.s", _CODE)
    write_file(tmp_path, "Left.l", "Right\n")
    write_file(tmp_path, "Right.s", _CODE)
    write_file(tmp_path, "Right.l", "AliasLeft\n")
    try:
        (tmp_path / "AliasLeft.s").symlink_to(tmp_path / "Left.s")
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot create a symlink")

    with pytest.raises(DependencyCycleError) as excinfo:
        SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Left"])

    assert excinfo.value.cycle[0] == excinfo.value.cycle[-1]
    assert {"left", "right", "aliasleft"} <= set(excinfo.value.cycle)


def test_first_body_match_wins_not_the_newest_datecode(tmp_path: Path) -> None:
    """LIB-01/DATE-01: the first matching body prefix wins.

    A later root with a much larger DateCode must not be preferred; a loader
    that "picks the newest" would silently load a different library version.
    """
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_file(first, "Lib.s", _CODE.replace("DateCode_ 1", "DateCode_ 10"))
    write_file(first, "Lib.l", "")
    write_file(second, "Lib.s", _CODE.replace("DateCode_ 1", "DateCode_ 9999"))
    write_file(second, "Lib.l", "")

    project = SattLineProject.load([first, second], LoadMode.DRAFT, ["Lib"])

    program = project.get("Lib")
    assert program.source_path == first / "Lib.s"
    assert program.code.datecode == 10


def test_load_parses_bodies_in_parallel_with_identical_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Base.s", _CODE)
    write_file(tmp_path, "Child.s", _CODE)
    write_file(tmp_path, "Child.l", "Base\n")
    write_file(tmp_path, "Leaf.s", _CODE)
    write_file(tmp_path, "Leaf.l", "Child\n")

    serial = _load(tmp_path, targets=("Leaf",), workers=1)
    dispatched = _record_dispatched(monkeypatch)
    parallel = _load(tmp_path, targets=("Leaf",), workers=3)

    # The parallel load must really use the pool, not fall back to this process.
    assert sorted(Path(path).name for path in dispatched) == ["Base.s", "Child.s", "Leaf.s"]
    assert serial.programs() == parallel.programs()
    assert serial.graph() == parallel.graph()
    assert serial.diagnostics() == parallel.diagnostics()


def test_a_parallel_debug_load_replays_each_files_parser_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker sends its bounded messages and the parent replays them in order."""
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Broken.s", _BROKEN)
    events: list[str] = []
    dispatched = _record_dispatched(monkeypatch)

    with pytest.raises(ArtifactLoadError):
        _load(tmp_path, targets=("Main", "Broken"), workers=2, debug=events)

    assert sorted(Path(path).name for path in dispatched) == ["Broken.s", "Main.s"]
    parsing = [event for event in events if event.startswith("Parsing:")]
    assert parsing == [f"Parsing: {tmp_path / 'Main.s'}", f"Parsing: {tmp_path / 'Broken.s'}"]


@pytest.mark.parametrize(
    ("broken_is_target", "expected"),
    [(True, ArtifactLoadError), (False, DependencyParseError)],
)
def test_a_broken_body_fails_the_same_way_in_parallel(
    tmp_path: Path,
    broken_is_target: bool,
    expected: type[ProjectLoadError],
) -> None:
    write_file(tmp_path, "Good.s", _CODE)
    write_file(tmp_path, "Good.l", "Broken\n")
    write_file(tmp_path, "Target.s", _CODE)
    write_file(tmp_path, "Target.l", "Good\n")
    write_file(tmp_path, "Broken.s", _BROKEN)

    targets = ("Broken",) if broken_is_target else ("Target",)
    with pytest.raises(expected):
        _load(tmp_path, targets=targets, workers=3)


def test_parallel_parse_falls_back_when_a_pool_cannot_be_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    def unavailable(max_workers: int) -> object:
        raise OSError(f"cannot start {max_workers} workers here")

    monkeypatch.setattr(project_loader_parallel, "process_pool", unavailable)
    with caplog.at_level("WARNING", logger="sattline_parser.project.executor"):
        project = _load(tmp_path, workers=2)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("worker pool unavailable" in record.message for record in caplog.records)


def test_parse_code_file_reads_but_never_writes_the_ast_cache(tmp_path: Path) -> None:
    """A worker reads the cache and leaves every write to the parent."""
    code = write_file(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    task = (str(code), LoadMode.DRAFT.value, str(cache_dir), True, False)

    first = parse_code_file(task)
    second = parse_code_file(task)

    assert first.ast is not None and first.failure is None
    assert second.ast is not None and second.failure is None
    assert not first.cached
    assert not second.cached
    assert second.ast == first.ast
    assert list((cache_dir / "file_ast").glob("*.pickle")) == []
    assert not (cache_dir / "file_ast" / ".parser-identity").exists()


def test_the_worker_cache_handle_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor_module, "_WORKER_CACHES", {})
    parent = project_loader.FileASTCache(tmp_path / "cache")  # the parent creates and maintains the layout
    marker = parent.cache_dir / ".parser-identity"
    stamp = marker.stat().st_mtime_ns

    handle = executor_module._worker_cache(str(tmp_path / "cache"))

    assert handle.enabled
    assert handle.read_only
    assert marker.stat().st_mtime_ns == stamp


def _ast_cache_snapshot(root: Path) -> dict[str, tuple[bytes | None, int]]:
    """Every path under *root* with its bytes (``None`` for a directory) and mtime."""
    snapshot: dict[str, tuple[bytes | None, int]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file():
            snapshot[relative] = (path.read_bytes(), path.stat().st_mtime_ns)
        else:
            snapshot[relative] = (None, path.stat().st_mtime_ns)
    return snapshot


def test_a_warm_parallel_load_leaves_the_ast_cache_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Workers must not prune, rewrite the marker, or move an entry's mtime."""
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")
    cache_dir = tmp_path / "cache"
    _load(tmp_path, cache_dir=cache_dir)
    ast_dir = cache_dir / "file_ast"
    assert len(list(ast_dir.glob("*.pickle"))) == 2
    before = _ast_cache_snapshot(ast_dir)

    dispatched = _record_dispatched(monkeypatch)
    project = _load(tmp_path, workers=2, cache_dir=cache_dir)

    assert tuple(project.programs()) == ("lib", "main")
    # The parallel load must really use the pool, so the workers read the cache.
    assert sorted(Path(path).name for path in dispatched) == ["Lib.s", "Main.s"]
    assert _ast_cache_snapshot(ast_dir) == before


def test_parse_code_file_reports_a_parse_failure_as_text(tmp_path: Path) -> None:
    code = write_file(tmp_path, "Broken.s", _BROKEN)

    outcome = parse_code_file((str(code), LoadMode.DRAFT.value, None, True, False))

    assert outcome.ast is None
    assert outcome.failure


def test_a_worker_returns_one_parser_message_per_file_under_debug(tmp_path: Path) -> None:
    code = write_file(tmp_path, "Main.s", _CODE)

    outcome = parse_code_file((str(code), LoadMode.DRAFT.value, None, True, True))

    assert outcome.debug[0] == f"Parsing: {code}"
    assert "Parse OK, transforming with SLTransformer" in outcome.debug
    assert len(outcome.debug) <= MAX_WORKER_DEBUG_MESSAGES


def test_worker_debug_messages_are_bounded_per_file() -> None:
    messages: list[str] = []
    for index in range(MAX_WORKER_DEBUG_MESSAGES + 5):
        executor_module._append_bounded_debug(messages, f"message {index}")

    assert len(messages) == MAX_WORKER_DEBUG_MESSAGES
    assert messages[-1] == f"message {MAX_WORKER_DEBUG_MESSAGES - 1}"


def test_a_decode_failure_record_keeps_a_bounded_buffer(tmp_path: Path) -> None:
    """A worker must not send the whole source buffer through the pipe."""
    code = tmp_path / "Huge.s"
    raw = b"a" * (256 * 1024) + b"\x81"
    code.write_bytes(raw)

    outcome = parse_code_file((str(code), LoadMode.DRAFT.value, None, False, False))

    record = outcome.failure_record
    assert record is not None
    assert record.unicode_error is not None
    encoding, excerpt, start, end, _reason = record.unicode_error
    assert encoding == "cp1252"
    assert len(excerpt) <= MAX_UNICODE_ERROR_BYTES
    assert (start, end) == (len(raw) - 1, len(raw))
    rebuilt = rebuild_parse_failure(record)
    assert isinstance(rebuilt, UnicodeDecodeError)
    assert (rebuilt.start, rebuilt.end) == (start, end)
    assert len(pickle.dumps(record)) < 4096


def test_a_failure_source_line_is_bounded(tmp_path: Path) -> None:
    code = write_file(tmp_path, "Long.s", "x" * (MAX_FAILURE_SOURCE_LINE * 4))

    outcome = parse_code_file((str(code), LoadMode.DRAFT.value, None, False, False))

    assert outcome.failure_record is not None
    assert outcome.failure_record.line == 1
    assert outcome.source_line is not None
    assert len(outcome.source_line) == MAX_FAILURE_SOURCE_LINE + len("...")
    assert outcome.source_line.endswith("...")


def test_a_failure_excerpt_is_absent_when_the_source_cannot_be_decoded() -> None:
    assert executor_module.failure_source_line(b"\x81", 1) is None
    # A line past the end of the text has no excerpt either.
    assert executor_module.failure_source_line(b"one line", 9) is None
    assert executor_module.failure_source_line(b"one line", None) is None


def test_a_worker_cache_hit_reports_its_debug_message(tmp_path: Path) -> None:
    code = write_file(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    project_loader.FileASTCache(cache_dir).save(code, LoadMode.DRAFT.value, parse_source_file(code))

    outcome = parse_code_file((str(code), LoadMode.DRAFT.value, str(cache_dir), True, True))

    assert outcome.cached
    assert outcome.debug == (f"Using cached AST for: {code}",)


def test_parse_code_file_serves_a_warm_entry_without_reparsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = write_file(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    project_loader.FileASTCache(cache_dir).save(code, LoadMode.DRAFT.value, parse_source_file(code))

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("a warm entry must not be reparsed")

    monkeypatch.setattr(executor_module, "parse_source_bytes", refuse)
    outcome = parse_code_file((str(code), LoadMode.DRAFT.value, str(cache_dir), True, False))

    assert outcome.ast is not None
    assert outcome.cached


def test_structural_error_during_assembly_fails_the_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cycle is structural, so assembly fails rather than skipping the program."""
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.g", _GFX)

    def structural(*args: object, **kwargs: object) -> object:
        raise DependencyCycleError(("main", "main"))

    monkeypatch.setattr(ProjectAssembler, "_load_companion", structural)
    with pytest.raises(DependencyCycleError):
        _load(tmp_path)


@pytest.mark.parametrize("workers", [1, 3])
def test_a_shared_dependency_is_parsed_once(tmp_path: Path, workers: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """A diamond parses the shared body once, whatever the worker count."""
    write_file(tmp_path, "Base.s", _CODE)
    write_file(tmp_path, "Left.s", _CODE)
    write_file(tmp_path, "Left.l", "Base\n")
    write_file(tmp_path, "Right.s", _CODE)
    # Same identity as Left's dependency, spelled differently.
    write_file(tmp_path, "Right.l", "base\n")
    write_file(tmp_path, "Top.s", _CODE)
    write_file(tmp_path, "Top.l", "Left\nRight\n")

    dispatched = _record_dispatched(monkeypatch) if workers > 1 else []
    project = _load(tmp_path, targets=("Top",), workers=workers)

    assert tuple(project.programs()) == ("base", "left", "right", "top")
    if workers > 1:
        names = sorted(Path(path).name for path in dispatched)
        assert names == ["Base.s", "Left.s", "Right.s", "Top.s"]


@pytest.mark.parametrize(
    ("methods", "threaded", "platform", "version", "expected"),
    [
        (["fork", "spawn", "forkserver"], False, "linux", (3, 13), "fork"),
        (["fork", "spawn", "forkserver"], True, "linux", (3, 13), "forkserver"),
        (["fork", "spawn"], True, "linux", (3, 13), "spawn"),
        (["fork"], True, "linux", (3, 13), None),
        (["fork", "spawn", "forkserver"], False, "darwin", (3, 13), None),
        (["forkserver", "spawn", "fork"], False, "linux", (3, 14), None),
        ([], False, "linux", (3, 13), None),
    ],
)
def test_start_method_never_forks_a_threaded_or_modern_process(
    methods: list[str], threaded: bool, platform: str, version: tuple[int, int], expected: str | None
) -> None:
    assert start_method(methods, threaded=threaded, platform=platform, version=version) == expected


def test_a_daemonic_parent_parses_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    def daemonic() -> object:
        return SimpleNamespace(daemon=True)

    monkeypatch.setattr(project_loader_parallel.multiprocessing, "current_process", daemonic)
    events: list[str] = []
    project = _load(tmp_path, workers=2, debug=events)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("daemonic" in event for event in events)


def test_parse_code_file_returns_a_cached_body_without_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = write_file(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    FileASTCache(cache_dir).save(code, LoadMode.DRAFT.value, parse_source_file(code))

    def no_parse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a cached body must not be parsed again")

    monkeypatch.setattr(executor_module, "parse_source_bytes", no_parse)
    outcome = parse_code_file((str(code), LoadMode.DRAFT.value, str(cache_dir), True, False))

    assert outcome.ast is not None and outcome.failure is None


class _FailingPool:
    """A pool whose workers die before returning a result."""

    def __enter__(self) -> _FailingPool:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def map(self, function: object, iterable: object, chunksize: int = 1) -> object:
        raise BrokenProcessPool("a worker died")

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        return None


def _failing_pool(max_workers: int) -> _FailingPool:
    return _FailingPool()


def test_a_dead_worker_pool_falls_back_to_this_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    monkeypatch.setattr(project_loader_parallel, "process_pool", _failing_pool)
    events: list[str] = []
    with caplog.at_level("WARNING", logger="sattline_parser.project.executor"):
        project = _load(tmp_path, workers=2, debug=events)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("pool failed" in event.lower() for event in events)
    assert any("worker pool failed" in record.message for record in caplog.records)


def test_a_cache_write_failure_does_not_fail_a_parallel_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    def failing_save(
        self: object,
        code_path: Path,
        mode: str,
        ast: BasePicture,
        *,
        snapshot: SourceSnapshot | None = None,
    ) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(project_loader.FileASTCache, "save", failing_save)
    events: list[str] = []
    project = _load(tmp_path, workers=2, cache_dir=tmp_path / "cache", debug=events)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("cache write failed" in event.lower() for event in events)


def test_a_parallel_save_records_the_snapshot_the_worker_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent must store the revision the worker read, not a later stat."""
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")
    seen: list[SourceSnapshot | None] = []
    real_save = FileASTCache.save

    def recording_save(
        self: FileASTCache,
        code_path: Path,
        mode: str,
        ast: BasePicture,
        *,
        snapshot: SourceSnapshot | None = None,
    ) -> None:
        seen.append(snapshot)
        real_save(self, code_path, mode, ast, snapshot=snapshot)

    monkeypatch.setattr(FileASTCache, "save", recording_save)
    _load(tmp_path, workers=2, cache_dir=tmp_path / "cache")

    assert seen == [source_snapshot(tmp_path / "Lib.s"), source_snapshot(tmp_path / "Main.s")]


def test_a_warm_parallel_load_does_not_rewrite_cached_bodies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")
    cache_dir = tmp_path / "cache"
    _load(tmp_path, cache_dir=cache_dir)
    saves: list[Path] = []

    def recording_save(
        self: FileASTCache,
        code_path: Path,
        mode: str,
        ast: BasePicture,
        *,
        snapshot: SourceSnapshot | None = None,
    ) -> None:
        saves.append(code_path)

    monkeypatch.setattr(FileASTCache, "save", recording_save)
    project = _load(tmp_path, workers=2, cache_dir=cache_dir)

    assert tuple(project.programs()) == ("lib", "main")
    assert saves == []


def test_a_body_that_changes_during_the_parse_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    def stale_snapshot(_path: Path, _raw_bytes: bytes | None = None) -> SourceSnapshot:
        return SourceSnapshot(mtime_ns=0, size=0, sha256="0" * 64)

    monkeypatch.setattr(executor_module, "source_snapshot", stale_snapshot)

    project = _load(tmp_path, cache_dir=tmp_path / "cache")

    assert "main" in project
    assert FileASTCache(tmp_path / "cache").load(tmp_path / "Main.s", LoadMode.DRAFT.value) is None


class _InterruptedPool:
    """A pool that is interrupted while bodies are still queued."""

    def __init__(self, shutdowns: list[dict[str, object]]) -> None:
        self._shutdowns = shutdowns

    def __enter__(self) -> _InterruptedPool:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def map(self, function: object, iterable: object, chunksize: int = 1) -> object:
        raise KeyboardInterrupt

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self._shutdowns.append({"wait": wait, "cancel_futures": cancel_futures})


#: Shutdown calls observed by :class:`_InterruptedPool`.
_SHUTDOWNS: list[dict[str, object]] = []


def _interrupted_pool(max_workers: int) -> _InterruptedPool:
    return _InterruptedPool(_SHUTDOWNS)


def test_an_interrupted_parallel_load_cancels_the_queued_bodies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    _SHUTDOWNS.clear()
    monkeypatch.setattr(project_loader_parallel, "process_pool", _interrupted_pool)

    with pytest.raises(KeyboardInterrupt):
        _load(tmp_path, workers=2)

    assert _SHUTDOWNS == [{"wait": False, "cancel_futures": True}]


def test_a_loader_resolves_one_load(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    loader = project_loader.ProjectLoader(
        roots=[tmp_path],
        mode=LoadMode.DRAFT,
        debug=None,
        cache_dir=None,
    )
    assert tuple(loader.resolve(["Main"])) == ("main",)

    with pytest.raises(RuntimeError, match="construct another loader"):
        loader.resolve(["Main"])


# --- resolved identity and target-set ownership -------------------------------

_HEADER = """\"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N\"
\"Original file date: ---\"
\"Program date: 2026-04-23-12:00:00.000, name: {name}\"
"""


def _source(name: str, *, typedefs: str = "", locals_block: str = "") -> str:
    return (
        _HEADER.format(name=name)
        + f"""
BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1
{typedefs}{locals_block}
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""
    )


_RECORD_TYPE = (
    "TYPEDEFINITIONS\n   SharedType = RECORD DateCode_ 1\n      Value: integer := 0;\n   ENDDEF (*SharedType*);\n"
)


def _two_roots_with_a_shared_unit(tmp_path: Path) -> tuple[Path, Path]:
    """Two roots, each with its own ``Util`` body, and one consumer per root.

    The two ``Util`` bodies differ: only the first root's declares ``SharedType``.
    """
    first = tmp_path / "r1"
    second = tmp_path / "r2"
    write_file(first, "Util.s", _source("Util", typedefs=_RECORD_TYPE))
    write_file(second, "Util.s", _source("Util"))
    for root, name in ((first, "Main1"), (second, "Main2")):
        write_file(
            root,
            f"{name}.s",
            _source(name, locals_block="LOCALVARIABLES\n   Sensor: SharedType;\n"),
        )
        write_file(root, f"{name}.l", "Util\n")
    return first, second


def test_a_same_named_unit_in_two_roots_resolves_to_the_first_root(tmp_path: Path) -> None:
    """Earlier roots win; the later body is never planned, parsed, or validated."""
    first, second = _two_roots_with_a_shared_unit(tmp_path)

    project = SattLineProject.load([first, second], LoadMode.DRAFT, ["Main1", "Main2"])

    assert set(project.programs()) == {"main1", "main2", "util"}
    assert project.get("Util").resolved_base == first.resolve()
    # Both consumers validate against the first root's Util, which declares
    # SharedType, so neither reports an unknown datatype.
    assert project.get("Main1").diagnostics == ()
    assert project.get("Main2").diagnostics == ()


@pytest.mark.parametrize("first_named", ["first", "second"])
def test_root_order_decides_which_same_named_body_wins(tmp_path: Path, first_named: str) -> None:
    first, second = _two_roots_with_a_shared_unit(tmp_path)
    roots = [first, second] if first_named == "first" else [second, first]
    winning = roots[0]

    project = SattLineProject.load(roots, LoadMode.DRAFT, ["Main1", "Main2"])

    assert project.get("Util").resolved_base == winning.resolve()
    assert project.get("Util").source_path == winning / "Util.s"


def _datecode_moduletype(datecode: int) -> str:
    return (
        "TYPEDEFINITIONS\n"
        f"   ControllerType = MODULEDEFINITION DateCode_ {datecode}\n"
        "   MODULEPARAMETERS\n"
        "      Setpoint: real := 0.0;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*ControllerType*);\n"
    )


@pytest.mark.parametrize("targets", [("Dep", "Main"), ("Main", "Dep")])
def test_a_target_reached_as_a_dependency_still_reports_its_datecode_conflict(
    tmp_path: Path, targets: tuple[str, str]
) -> None:
    """Ownership comes from the target set, not from discovery order."""
    write_file(tmp_path, "Base.s", _source("Base", typedefs=_datecode_moduletype(1)))
    write_file(tmp_path, "Dep.s", _source("Dep", typedefs=_datecode_moduletype(2)))
    write_file(tmp_path, "Dep.l", "Base\n")
    write_file(tmp_path, "Main.s", _source("Main"))

    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, targets)

    conflicts = [d.code.value for d in project.get("Dep").diagnostics]
    assert conflicts == ["SL-V057"]


def test_an_oversize_distribution_companion_is_a_load_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.p", _DISTRIBUTION)
    monkeypatch.setattr("sattline_parser.project.distribution.MAX_DISTRIBUTION_COMPANION_BYTES", 4)

    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)

    assert "byte limit" in str(exc_info.value)


def test_an_oversize_graphics_companion_is_a_load_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.g", _GFX)
    monkeypatch.setattr("sattline_parser.project.graphics_parsing.MAX_GRAPHICS_COMPANION_BYTES", 4)

    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)

    assert "byte limit" in str(exc_info.value)


def test_an_oversize_dependency_companion_is_a_dependency_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Lib.p", _DISTRIBUTION)
    monkeypatch.setattr("sattline_parser.project.distribution.MAX_DISTRIBUTION_COMPANION_BYTES", 4)

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.dependency == "Lib"


def test_diagnose_keeps_the_list_and_the_set_in_step(tmp_path: Path) -> None:
    loader = project_loader.ProjectLoader(
        roots=[tmp_path],
        mode=LoadMode.DRAFT,
        debug=None,
        cache_dir=None,
    )
    loader._diagnose(LoadDiagnosticKind.SIDECAR_MISSING, "A", "same detail")
    loader._diagnose(LoadDiagnosticKind.SIDECAR_MISSING, "A", "same detail")

    assert len(loader.diagnostics) == 1
    assert len(loader._diagnostic_set) == 1


def test_plan_key_falls_back_to_the_raw_path_when_resolve_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(_path: Path) -> Path:
        raise OSError("boom")

    monkeypatch.setattr(Path, "resolve", _raise)

    assert plan_module.plan_key(Path("/missing/Prog.s")) == ArtifactIdentity.of(Path("/missing/Prog.s")).key


def test_a_structural_error_escapes_the_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    def _raise(*_args: object, **_kwargs: object) -> object:
        raise StructuralProjectError("Main", "structural")

    monkeypatch.setattr(ProjectPlanner, "resolve_artifact", _raise)

    with pytest.raises(StructuralProjectError, match="structural"):
        _load(tmp_path)


def test_a_debug_load_reports_companion_parsing(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.p", _DISTRIBUTION)
    events: list[str] = []

    _load(tmp_path, debug=events)

    assert any("Parsing distribution" in event for event in events)


def test_the_worker_entry_point_defaults_to_the_package_parser(tmp_path: Path) -> None:
    code = write_file(tmp_path, "Main.s", _CODE)

    outcome = executor_module.parse_code_file((str(code), LoadMode.DRAFT.value, None, False, False))

    assert outcome.ast is not None
    assert outcome.failure is None


# --- unit identity, aliases, and planning scale -------------------------------


def test_a_twenty_one_character_target_name_loads(tmp_path: Path) -> None:
    """The length of a name is ``SL-V038`` at the declaration, not a load failure."""
    name = "ABCDEFGHIJKLMNOPQRSTU"
    assert len(name) == 21
    write_file(tmp_path, f"{name}.s", _source(name))

    project = _load(tmp_path, targets=(name,))

    assert project.get(name).source_path == tmp_path / f"{name}.s"


def test_a_dependency_spelling_resolves_by_language_identity(tmp_path: Path) -> None:
    """``STRASSE`` is not ``Straße`` even though ``str.casefold`` equates them."""
    write_file(tmp_path, "Main.s", _source("Main"))
    write_file(tmp_path, "Main.l", "STRASSE\n")
    write_file(tmp_path, "Straße.s", _source("Sharp"))
    write_file(tmp_path, "STRASSE.s", _source("Upper"))

    project = _load(tmp_path)

    assert project.get("STRASSE").source_path == tmp_path / "STRASSE.s"
    assert "Straße" not in project


def test_a_casefold_only_lookup_does_not_designate_a_loaded_unit(tmp_path: Path) -> None:
    write_file(tmp_path, "Straße.s", _source("Sharp"))

    project = _load(tmp_path, targets=("Straße",))

    assert project.get("Straße").name == "Straße"
    assert project.get("straße").name == "Straße"
    # Every view key round-trips, even one the language fold would not produce.
    for key in project.programs():
        assert project.get(key).name == "Straße"
    with pytest.raises(KeyError, match="no loaded program"):
        project.get("STRASSE")
    assert "STRASSE" not in project


def test_dependents_of_accepts_a_view_key_and_rejects_a_casefold_only_name(tmp_path: Path) -> None:
    write_file(tmp_path, "Straße.s", _source("Sharp"))
    write_file(tmp_path, "Main.s", _source("Main"))
    (tmp_path / "Main.l").write_text("Straße\n", encoding="cp1252")

    project = _load(tmp_path)

    assert set(project.programs()) == {"main", "strasse"}
    assert project.dependents_of("Straße") == ("Main",)
    # ``strasse`` is the view key ``programs()`` reports for ``Straße``.
    assert project.dependents_of("strasse") == ("Main",)
    # ``STRASSE`` is a different unit, so nothing depends on it.
    assert project.dependents_of("STRASSE") == ()


def test_a_folded_name_collision_is_reported_and_one_unit_wins(tmp_path: Path, case_sensitive_fs: None) -> None:
    """Two files the language considers one unit are reported, not dropped."""
    write_file(tmp_path, "Util.s", _source("Util"))
    write_file(tmp_path, "UTIL.s", _source("UTIL"))

    project = _load(tmp_path, targets=("Util",))

    collisions = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.FOLDED_NAME_COLLISION]
    assert len(collisions) == 1
    assert "UTIL.s" in collisions[0].detail
    assert "Util.s" in collisions[0].detail
    assert collisions[0].path == tmp_path / "UTIL.s"
    assert project.get("Util").source_path == tmp_path / "UTIL.s"


def test_two_units_that_casefold_together_both_stay_in_the_view(tmp_path: Path) -> None:
    """A shared casefold key names no unit; both use their language identity."""
    write_file(tmp_path, "Straße.s", _source("Sharp"))
    write_file(tmp_path, "STRASSE.s", _source("Upper"))

    project = _load(tmp_path, targets=("Straße", "STRASSE"))

    collisions = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.FOLDED_NAME_COLLISION]
    assert len(collisions) == 1
    assert "Straße" in collisions[0].detail
    assert "STRASSE" in collisions[0].detail
    assert list(project.programs()) == ["STRAßE", "STRASSE"]
    assert project.get("Straße").source_path == tmp_path / "Straße.s"
    assert project.get("STRAßE").source_path == tmp_path / "Straße.s"
    # ``strasse`` is the language identity of the lowercase spelling, not a view key.
    assert project.get("strasse").source_path == tmp_path / "STRASSE.s"
    assert project.get("STRASSE").source_path == tmp_path / "STRASSE.s"


def test_a_folded_name_collision_round_trips_and_never_retargets_an_edge(tmp_path: Path) -> None:
    """A dependency on either unit of a shared casefold key names that unit."""
    write_file(tmp_path, "Straße.s", _source("Sharp"))
    write_file(tmp_path, "STRASSE.s", _source("Upper"))
    write_file(tmp_path, "Main.s", _source("Main"))
    (tmp_path / "Main.l").write_text("STRASSE\n", encoding="cp1252")

    project = _load(tmp_path, targets=("Straße", "STRASSE", "Main"))

    assert project.get("STRASSE").source_path == tmp_path / "STRASSE.s"
    # ``dependencies_of`` returns a declared name ``get`` resolves to the same unit.
    (dependency,) = project.dependencies_of("Main")
    assert dependency == "STRASSE"
    assert project.get(dependency).source_path == tmp_path / "STRASSE.s"
    assert project.dependents_of("STRASSE") == ("Main",)
    assert project.dependents_of("strasse") == ("Main",)
    # The graph points at the unit the declaration named, not at the other one.
    graph = project.graph()
    assert set(graph.nodes) == {"STRAßE", "STRASSE", "main"}
    assert graph.edges == (("main", "STRASSE"),)
    assert graph.dependencies_of("Main") == ("STRASSE",)
    assert graph.dependents_of("STRASSE") == ("main",)
    assert graph.dependents_of("Straße") == ()


def test_a_lowercase_spelling_of_the_shared_key_round_trips(tmp_path: Path) -> None:
    """``strasse`` is the language name of ``strasse.s``, not a view-key alias."""
    write_file(tmp_path, "Straße.s", _source("Sharp"))
    write_file(tmp_path, "strasse.s", _source("Lower"))
    write_file(tmp_path, "Main.s", _source("Main"))
    (tmp_path / "Main.l").write_text("strasse\n", encoding="cp1252")

    project = _load(tmp_path, targets=("Straße", "strasse", "Main"))

    assert project.get("strasse").source_path == tmp_path / "strasse.s"
    (dependency,) = project.dependencies_of("Main")
    assert dependency == "strasse"
    assert project.get(dependency).source_path == tmp_path / "strasse.s"
    assert project.dependents_of("strasse") == ("Main",)
    assert project.graph().edges == (("main", "STRASSE"),)


def test_an_alias_spelling_does_not_answer_for_a_casefold_only_name(tmp_path: Path) -> None:
    """An alias resolves under the spelling that reached it, not under casefold."""
    write_file(tmp_path, "Base.s", _source("Base"))
    try:
        (tmp_path / "Straße.s").symlink_to(tmp_path / "Base.s")
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot create a symlink")
    write_file(tmp_path, "Main.s", _source("Main"))
    # Sidecars are CP1252, so a sharp s must be written in the file's encoding.
    (tmp_path / "Main.l").write_text("Base\nStraße\n", encoding="cp1252")

    project = _load(tmp_path)

    assert project.get("Straße").name == "Base"
    assert project.get("straße").name == "Base"
    with pytest.raises(KeyError, match="no loaded program"):
        project.get("STRASSE")
    assert "STRASSE" not in project


def test_an_alias_dependency_name_resolves_to_the_unit_it_reached(tmp_path: Path) -> None:
    """One body named twice keeps both names, and the graph stays closed."""
    write_file(tmp_path, "Base.s", _source("Base"))
    try:
        (tmp_path / "AliasBase.s").symlink_to(tmp_path / "Base.s")
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot create a symlink")
    write_file(tmp_path, "Main.s", _source("Main"))
    write_file(tmp_path, "Main.l", "Base\nAliasBase\n")

    project = _load(tmp_path)

    assert project.dependencies_of("Main") == ("Base", "AliasBase")
    for name in project.dependencies_of("Main"):
        assert project.get(name).name == "Base"
    # Both spellings name the same unit, so both answer for its dependents.
    assert project.dependents_of("Base") == ("Main",)
    assert project.dependents_of("AliasBase") == ("Main",)
    graph = project.graph()
    assert set(graph.nodes) == {"base", "main"}
    assert set(graph.edges) == {("main", "base")}
    assert graph.dependents_of("AliasBase") == ()


def test_a_second_visit_to_the_same_body_does_not_report_an_unused_sidecar(tmp_path: Path) -> None:
    """A diamond and two targets sharing a dependency are not aliases.

    The shared body's sidecar is read on the first visit. Every later visit
    resolves the same prefix, so nothing was left unread and the load must not
    claim otherwise.
    """
    write_file(tmp_path, "Leaf.s", _source("Leaf"))
    write_file(tmp_path, "Base.s", _source("Base"))
    write_file(tmp_path, "Base.l", "Leaf\n")
    for name, dependencies in (("Left", "Base\n"), ("Right", "Base\n"), ("Top", "Left\nRight\n")):
        write_file(tmp_path, f"{name}.s", _source(name))
        write_file(tmp_path, f"{name}.l", dependencies)

    project = _load(tmp_path, targets=("Top", "Left", "Right"))

    assert project.dependencies_of("Base") == ("Leaf",)
    assert project.dependents_of("Base") == ("Left", "Right")
    kinds = [diagnostic.kind for diagnostic in project.diagnostics()]
    assert LoadDiagnosticKind.ALIAS_DECLARATIONS_UNUSED not in kinds


def test_an_alias_sidecar_declaration_is_reported_and_not_loaded(tmp_path: Path) -> None:
    """A spelling that reaches a planned body never contributes dependencies."""
    write_file(tmp_path, "Util.s", _source("Util"))
    write_file(tmp_path, "Extra.s", _source("Extra"))
    try:
        (tmp_path / "Helper.s").symlink_to(tmp_path / "Util.s")
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot create a symlink")
    write_file(tmp_path, "Helper.l", "Extra\n")

    project = _load(tmp_path, targets=("Util", "Helper"))

    assert "Extra" not in project
    assert [program.name for program in project.programs().values()] == ["Util"]
    unused = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.ALIAS_DECLARATIONS_UNUSED]
    assert len(unused) == 1
    assert unused[0].program == "Helper"
    assert unused[0].path == tmp_path / "Helper.l"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")
def test_an_unreadable_alias_sidecar_does_not_fail_the_load(tmp_path: Path) -> None:
    """The alias prefix's sidecar is resolved but never read."""
    write_file(tmp_path, "Util.s", _source("Util"))
    try:
        (tmp_path / "Helper.s").symlink_to(tmp_path / "Util.s")
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot create a symlink")
    sidecar = write_file(tmp_path, "Helper.l", "Extra\n")
    sidecar.chmod(0)
    try:
        project = _load(tmp_path, targets=("Util", "Helper"))
    finally:
        sidecar.chmod(0o644)

    assert [program.name for program in project.programs().values()] == ["Util"]
    kinds = {d.kind for d in project.diagnostics()}
    assert LoadDiagnosticKind.ALIAS_DECLARATIONS_UNUSED in kinds


def _write_chain(root: Path, length: int, *, close: bool) -> None:
    """Write ``Unit0`` .. ``Unit{length-1}``, each depending on the next."""
    for index in range(length):
        name = f"Unit{index}"
        write_file(root, f"{name}.s", _source(name))
        if index + 1 < length:
            write_file(root, f"{name}.l", f"Unit{index + 1}\n")
        elif close:
            write_file(root, f"{name}.l", "Unit0\n")


def test_a_four_hundred_unit_cycle_is_a_cycle_not_a_recursion_error(tmp_path: Path) -> None:
    _write_chain(tmp_path, 400, close=True)

    with pytest.raises(DependencyCycleError) as excinfo:
        _load(tmp_path, targets=("Unit0",))

    cycle = excinfo.value.cycle
    assert cycle[0] == cycle[-1]
    assert len(cycle) == 401


def test_a_four_hundred_unit_chain_loads(tmp_path: Path) -> None:
    _write_chain(tmp_path, 400, close=False)

    project = _load(tmp_path, targets=("Unit0",))

    assert len(project.programs()) == 400
    assert project.dependencies_of("Unit0") == ("Unit1",)
    assert project.dependencies_of("Unit399") == ()


# --- companion resolution, skipped files, roots, and nested pools --------------


def test_companion_resolution_scans_each_directory_once_per_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Graphics, distribution, and the sidecar probe share one directory scan."""
    targets = tuple(f"Unit{index}" for index in range(24))
    for name in targets:
        write_file(tmp_path, f"{name}.s", _source(name))
    scans: list[Path] = []
    original = CompanionIndex._scan

    def counting(self: CompanionIndex, base: Path) -> dict[tuple[str, str], tuple[Path, ...]]:
        if base not in self._entries:
            scans.append(base)
        return original(self, base)

    monkeypatch.setattr(CompanionIndex, "_scan", counting)

    first = _load(tmp_path, targets=targets)

    assert len(first.programs()) == 24
    assert scans == [tmp_path.resolve()]

    scans.clear()
    _load(tmp_path, targets=targets)

    # A second load owns a fresh index: the cache never crosses a load.
    assert scans == [tmp_path.resolve()]


def test_a_companion_in_the_other_family_is_reported_and_not_paired(tmp_path: Path) -> None:
    """A ``.y`` beside a ``.s`` body explains why the graphics answer is missing."""
    write_file(tmp_path, "Main.s", _source("Main"))
    write_file(tmp_path, "Main.y", "")
    write_file(tmp_path, "Main.q", "")

    project = _load(tmp_path)

    program = project.get("Main")
    assert program.graphics is None
    assert program.distribution is None
    assert program.has_executing_system is None
    mismatches = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.COMPANION_FAMILY_MISMATCH]
    assert {diagnostic.path for diagnostic in mismatches} == {tmp_path / "Main.y", tmp_path / "Main.q"}
    assert {diagnostic.program for diagnostic in mismatches} == {"Main"}


def test_a_paired_companion_does_not_report_the_other_family(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _source("Main"))
    write_file(tmp_path, "Main.g", _GFX)
    write_file(tmp_path, "Main.y", "")
    write_file(tmp_path, "Main.p", _DISTRIBUTION_EMPTY)
    write_file(tmp_path, "Main.q", "")

    project = _load(tmp_path)

    assert project.get("Main").graphics is not None
    assert project.get("Main").has_executing_system is False
    assert not [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.COMPANION_FAMILY_MISMATCH]


def test_a_companion_name_collision_is_reported_with_its_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_sensitive_fs: None
) -> None:
    """The alphabetically first case variant pairs, whatever order the directory lists."""
    write_file(tmp_path, "main.s", _source("Main"))
    winner = write_file(tmp_path, "MAIN.G", _GFX)
    loser = write_file(tmp_path, "Main.g", _GFX_UNTERMINATED)
    original = Path.iterdir

    def reversed_entries(self: Path) -> list[Path]:
        return sorted(original(self), key=lambda entry: entry.name, reverse=True)

    monkeypatch.setattr(Path, "iterdir", reversed_entries)

    project = _load(tmp_path)

    assert project.get("Main").graphics is not None
    collisions = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.FOLDED_NAME_COLLISION]
    assert len(collisions) == 1
    assert collisions[0].path == winner
    assert "MAIN.G" in collisions[0].detail
    assert loser.name in collisions[0].detail


def test_a_sidecar_that_matches_only_under_casefold_is_not_a_family_mismatch(tmp_path: Path) -> None:
    """The other-family probe uses language identity, not ``str.casefold``."""
    write_file(tmp_path, "Straße.s", _source("Sharp"))
    write_file(tmp_path, "STRASSE.z", "")

    project = _load(tmp_path, targets=("Straße",))

    kinds = {diagnostic.kind for diagnostic in project.diagnostics()}
    assert LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH not in kinds
    assert LoadDiagnosticKind.SIDECAR_MISSING in kinds


def test_a_code_file_whose_stem_is_not_a_unit_name_is_reported_and_skipped(tmp_path: Path) -> None:
    """A dotted stem cannot be a target; the load names it and carries on."""
    write_file(tmp_path, "Main.s", _source("Main"))
    write_file(tmp_path, "Pump.v2.s", _source("Pump"))

    project = _load(tmp_path, targets=("Main",))

    assert set(project.programs()) == {"main"}
    skipped = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.SKIPPED_FILE]
    assert len(skipped) == 1
    assert skipped[0].program == "Pump.v2"
    assert skipped[0].path == tmp_path / "Pump.v2.s"
    assert "Pump.v2.s" in skipped[0].detail


def test_a_code_file_with_a_dotted_stem_is_not_a_discovered_target(tmp_path: Path) -> None:
    """The default discovery rule and the resolver share one name predicate."""
    write_file(tmp_path, "Main.s", _source("Main"))
    write_file(tmp_path, "Pump.v2.s", _source("Pump"))

    assert _discover_targets([tmp_path], mode=LoadMode.DRAFT) == ("Main",)


def test_a_skipped_candidate_outside_the_requested_mode_is_not_reported(tmp_path: Path) -> None:
    """Official mode does not consider a draft body, so it is not a skipped target."""
    write_file(tmp_path, "Main.x", _source("Main"))
    write_file(tmp_path, "Pump.v2.s", _source("Pump"))

    project = _load(tmp_path, targets=("Main",), mode=LoadMode.OFFICIAL)

    assert not [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.SKIPPED_FILE]


def test_a_root_that_is_a_file_is_a_load_error_naming_it(tmp_path: Path) -> None:
    """A file root is not an empty root: the load names the root and stops."""
    root = write_file(tmp_path, "notes.txt", "not a library")

    with pytest.raises(ProjectLoadError, match="not a readable directory") as excinfo:
        SattLineProject.load([root], LoadMode.DRAFT, ["Main"])

    assert str(root) in str(excinfo.value)


def test_a_missing_root_is_a_load_error_naming_it(tmp_path: Path) -> None:
    missing = tmp_path / "absent"

    with pytest.raises(ProjectLoadError, match="not a readable directory") as excinfo:
        SattLineProject.load([missing], LoadMode.DRAFT, ["Main"])

    assert str(missing) in str(excinfo.value)


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="mode bits deny reads on POSIX, and root bypasses them",
)
def test_a_root_under_a_denied_ancestor_is_a_load_error(tmp_path: Path) -> None:
    closed = tmp_path / "closed"
    root = closed / "libs"
    root.mkdir(parents=True)
    closed.chmod(0o000)
    try:
        with pytest.raises(ProjectLoadError, match="not a readable directory") as excinfo:
            SattLineProject.load([root], LoadMode.DRAFT, ["Main"])
    finally:
        closed.chmod(0o755)

    assert str(root) in str(excinfo.value)


def test_pool_allowed_rejects_a_process_that_belongs_to_an_outer_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(project_loader_parallel.multiprocessing, "parent_process", lambda: object())

    assert pool_allowed() is False


def test_pool_allowed_rejects_a_marked_pool_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(project_loader_parallel.POOL_WORKER_ENV, "1")

    assert pool_allowed() is False


def test_a_pool_worker_marks_itself_before_it_runs_a_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(project_loader_parallel.POOL_WORKER_ENV, raising=False)

    project_loader_parallel._mark_pool_worker()  # pyright: ignore[reportPrivateUsage]

    try:
        assert pool_allowed() is False
    finally:
        # ``_mark_pool_worker`` writes the environment directly, so the marker
        # would otherwise leak into every later test in this process.
        os.environ.pop(project_loader_parallel.POOL_WORKER_ENV, None)


def test_a_nested_load_parses_in_this_process_and_says_so_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for index in range(3):
        write_file(tmp_path, f"Unit{index}.s", _source(f"Unit{index}"))
    calls: list[int] = []

    def forbidden(max_workers: int) -> NoReturn:
        calls.append(max_workers)
        raise AssertionError("a nested load must not start a worker pool")

    monkeypatch.setattr(project_loader_parallel, "process_pool", forbidden)

    with caplog.at_level(logging.WARNING), load_in_progress():
        assert loads_in_progress() == 1
        loader = project_loader.ProjectLoader(
            roots=[tmp_path],
            mode=LoadMode.DRAFT,
            debug=None,
            cache_dir=None,
            workers=4,
        )
        registry = loader.resolve(("Unit0", "Unit1", "Unit2"))

    assert calls == []
    assert len(registry) == 3
    warnings = [record for record in caplog.records if "worker pool not started" in record.getMessage()]
    assert len(warnings) == 1
    assert loads_in_progress() == 0
