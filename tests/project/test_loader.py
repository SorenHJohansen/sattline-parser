# pyright: reportPrivateUsage=false
"""Unit tests for Phase 3 recursive program loading (``project/loader.py``)."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sattline_parser.api import parse_source_file
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.project import (
    ArtifactLoadError,
    DependencyCycleError,
    DependencyNotFoundError,
    DependencyParseError,
    LoadMode,
    ProjectLoadError,
    SattLineProject,
    read_dependency_names,
)
from sattline_parser.project import loader as project_loader
from sattline_parser.project.ast_cache import FileASTCache
from sattline_parser.project.models import LoadDiagnosticKind, SidecarState

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


def _write(root: Path, rel: str, content: str = "") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _load(
    root: Path,
    *,
    targets: tuple[str, ...] = ("Main",),
    mode: LoadMode = LoadMode.DRAFT,
    strict: bool = True,
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
        strict=strict,
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
    real_factory = project_loader._process_pool
    seen: list[str] = []

    def factory(max_workers: int) -> _RecordingPool:
        return _RecordingPool(real_factory(max_workers), seen)

    monkeypatch.setattr(project_loader, "_process_pool", factory)
    return seen


def _counting_parse(call_count: list[int]) -> Callable[..., BasePicture]:
    real_parse = parse_source_file

    def counting_parse(code_path: Path, **_: object) -> BasePicture:
        call_count.append(1)
        return real_parse(code_path)

    return counting_parse


def test_read_dependency_names_trim_and_ignore_blanks(tmp_path: Path) -> None:
    deps = tmp_path / "Main.l"
    deps.write_text("  Lib1  \n\n Lib2\t\n\n\n  \nLib3\n", encoding="utf-8")
    assert read_dependency_names(deps) == ("Lib1", "Lib2", "Lib3")


def test_load_resolves_single_target(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
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
    _write(tmp_path, "A.s", _CODE)
    _write(tmp_path, "B.s", _CODE)
    project = _load(tmp_path, targets=("A", "B"))
    assert ("a" in project) and ("b" in project)
    assert len(project.programs()) == 2


def test_load_recursive_dependencies(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib1\nLib2\n")
    _write(tmp_path, "Lib1.s", _CODE)
    _write(tmp_path, "Lib1.l", "Lib2\n")
    _write(tmp_path, "Lib2.s", _CODE)
    project = _load(tmp_path)
    assert project.dependencies_of("Main") == ("Lib1", "Lib2")
    assert project.dependencies_of("Lib1") == ("Lib2",)
    assert project.dependencies_of("Lib2") == ()
    assert set(project.programs()) == {"main", "lib1", "lib2"}


def test_load_diamond_dependency_loads_once(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "A\nB\n")
    _write(tmp_path, "A.s", _CODE)
    _write(tmp_path, "A.l", "C\n")
    _write(tmp_path, "B.s", _CODE)
    _write(tmp_path, "B.l", "C\n")
    _write(tmp_path, "C.s", _CODE)
    project = _load(tmp_path)
    assert len(project.programs()) == 4
    assert project.dependents_of("C") == ("a", "b")
    assert project.graph().nodes == ("a", "b", "c", "main")


def test_load_duplicate_dependency_loads_once(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib\nLib\n")
    _write(tmp_path, "Lib.s", _CODE)
    project = _load(tmp_path)
    assert len(project.programs()) == 2
    assert project.dependencies_of("Main") == ("Lib", "Lib")
    assert project.graph().edges.count(("main", "lib")) == 2


def test_load_cycle_is_an_error_not_an_edge(tmp_path: Path) -> None:
    _write(tmp_path, "A.s", _CODE)
    _write(tmp_path, "A.l", "B\n")
    _write(tmp_path, "B.s", _CODE)
    _write(tmp_path, "B.l", "A\n")
    with pytest.raises(DependencyCycleError):
        _load(tmp_path, targets=("A",))


def test_load_targets_canonicalized_by_case(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    project = _load(tmp_path, targets=("Main", "MAIN"))
    assert len(project.programs()) == 1
    assert project.get("mAiN").name == "Main"


def test_load_resolves_dependencies_across_roots(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    library = tmp_path / "library"
    _write(consumer, "Client.s", _CODE)
    _write(consumer, "Client.l", "LibA\n")
    _write(library, "LibA.s", _CODE)
    _write(library, "LibA.l", "LibB\n")
    _write(consumer, "LibB.s", _CODE)
    _write(consumer, "LibB.l", "ConsumerSide\n")
    _write(library, "LibB.s", _CODE)
    _write(library, "LibB.l", "LibrarySide\n")
    _write(consumer, "ConsumerSide.s", _CODE)
    _write(library, "LibrarySide.s", _CODE)

    project = SattLineProject.load([consumer, library], LoadMode.DRAFT, ["Client"])

    assert project.dependencies_of("Client") == ("LibA",)
    assert project.dependencies_of("LibA") == ("LibB",)
    assert project.dependencies_of("LibB") == ("LibrarySide",)
    assert project.dependencies_of("LibrarySide") == ()


def test_load_missing_dependency_strict_raises(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Ghost\n")
    with pytest.raises(DependencyNotFoundError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Ghost"


def test_load_missing_target_raises_without_dependency(tmp_path: Path) -> None:
    _write(tmp_path, "Other.s", _CODE)
    with pytest.raises(DependencyNotFoundError) as exc_info:
        _load(tmp_path, targets=("Ghost",))
    assert exc_info.value.program == "Ghost"
    assert exc_info.value.dependency is None


def test_load_target_parse_failure_raises_artifact_error(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _BROKEN)
    with pytest.raises(ArtifactLoadError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency is None


def test_load_dependency_parse_failure_raises_dependency_error(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Broken\n")
    _write(tmp_path, "Broken.s", _BROKEN)
    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Broken"


def test_load_unreadable_deps_file_raises(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").mkdir(exist_ok=True)
    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency is None


def test_load_strict_false_skips_missing_dependency(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Ghost\n")
    _write(tmp_path, "Ok.s", _CODE)
    project = _load(tmp_path, targets=("Ok", "Main"), strict=False)
    assert "ok" in project and "main" in project
    assert "ghost" not in project
    assert project.dependencies_of("Main") == ("Ghost",)
    assert ("main", "ghost") in project.graph().edges
    skipped = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.LOAD_SKIPPED]
    assert [d.program for d in skipped] == ["Ghost"]
    assert "missing code file" in skipped[0].detail


def test_load_strict_false_skips_broken_code(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Broken\n")
    _write(tmp_path, "Broken.s", _BROKEN)
    _write(tmp_path, "Ok.s", _CODE)
    project = _load(tmp_path, targets=("Ok", "Main"), strict=False)
    assert "ok" in project and "main" in project
    assert "broken" not in project
    skipped = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.LOAD_SKIPPED]
    assert [d.program for d in skipped] == ["Broken"]
    assert "failed to parse" in skipped[0].detail


def test_load_draft_fallback_extensions(tmp_path: Path) -> None:
    _write(tmp_path, "Main.x", _CODE)
    _write(tmp_path, "Main.z", "Lib\n")
    _write(tmp_path, "Lib.x", _CODE)
    project = _load(tmp_path)
    assert project.get("Main").format.code_ext == ".x"
    assert project.get("Main").format.deps_ext == ".z"
    assert project.get("Main").format.mode is LoadMode.DRAFT


def test_load_arbitrary_graphics_companion_does_not_raise(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.g", "GRAPHICS")
    project = _load(tmp_path)
    program = project.programs()["main"]
    assert program.graphics is not None
    assert program.graphics.messages == ()


def test_load_empty_targets(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    project = _load(tmp_path, targets=())
    assert len(project.programs()) == 0


def test_load_debug_callback(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    debug: list[str] = []
    _load(tmp_path, debug=debug)
    assert any("Visiting: Main" in line for line in debug)
    assert any("Parsing:" in line for line in debug)


@contextmanager
def _spy_on_parse(call_count: list[int]) -> Generator[None]:
    with patch.object(project_loader, "parse_source_file", side_effect=_counting_parse(call_count)):
        yield


def test_load_ast_cache_reuses_parsed_programs(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib\n")
    _write(tmp_path, "Lib.s", _CODE)
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
    _write(tmp_path, "Main.s", _CODE)
    call_count: list[int] = []
    with _spy_on_parse(call_count):
        _load(tmp_path)
        first = len(call_count)
        _load(tmp_path)
        second = len(call_count)

    assert first == 1
    assert second == 2


def test_load_fails_closed_when_the_cache_root_is_foreign(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr("sattline_parser.source_io._getuid", lambda: -1)

    project = _load(tmp_path, cache_dir=cache_dir)

    assert "main" in project
    assert not (cache_dir / "file_lookup_cache.json").exists()
    assert not (cache_dir / "file_ast").exists()


def test_load_ast_cache_reparses_after_source_change(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    cache_dir = tmp_path / "cache"
    call_count: list[int] = []
    with _spy_on_parse(call_count):
        first = _load(tmp_path, cache_dir=cache_dir)
        assert len(call_count) == 1
        _write(tmp_path, "Main.s", _CODE + "\n")
        second = _load(tmp_path, cache_dir=cache_dir)

    assert "main" in first and "main" in second
    assert len(call_count) == 2


# --- Phase 4: graphics companion wiring ----------------------------------------


def test_load_parses_graphics_companion(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.g", _GFX)

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


def test_load_draft_falls_back_to_official_graphics_ext(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.y", _GFX)

    program = _load(tmp_path).programs()["main"]

    assert program.format.graphics_ext == ".y"
    assert program.graphics is not None


def test_load_without_graphics_companion(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)

    program = _load(tmp_path).programs()["main"]

    assert program.format.graphics_ext is None
    assert program.graphics is None


def test_load_official_mode_ignores_draft_graphics(tmp_path: Path) -> None:
    _write(tmp_path, "Main.x", _CODE)
    _write(tmp_path, "Main.g", _GFX)

    program = _load(tmp_path, mode=LoadMode.OFFICIAL).programs()["main"]

    assert program.format.graphics_ext is None
    assert program.graphics is None


def test_load_official_mode_uses_official_graphics(tmp_path: Path) -> None:
    _write(tmp_path, "Main.x", _CODE)
    _write(tmp_path, "Main.y", _GFX)

    program = _load(tmp_path, mode=LoadMode.OFFICIAL).programs()["main"]

    assert program.format.graphics_ext == ".y"
    assert program.graphics is not None


def test_load_x_code_only_accepts_official_graphics(tmp_path: Path) -> None:
    _write(tmp_path, "Main.x", _CODE)
    _write(tmp_path, "Main.g", _GFX)
    _write(tmp_path, "Main.y", _GFX)

    program = _load(tmp_path).programs()["main"]

    assert program.format.graphics_ext == ".y"
    assert program.graphics is not None


def test_load_graphics_read_failure_strict_raises(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.g").mkdir()

    with pytest.raises(ArtifactLoadError):
        _load(tmp_path)


def test_load_graphics_read_failure_non_strict_skips(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.g").mkdir()

    project = _load(tmp_path, strict=False)

    assert "main" not in project


def test_load_dependency_graphics_read_failure_raises_dependency_parse_error(tmp_path: Path) -> None:
    _write(tmp_path, "Main.l", "Lib\n")
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Lib.s", _CODE)
    (tmp_path / "Lib.g").mkdir()

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Lib"


# --- sidecar pairing invariant ----------------------------------------------


def test_load_dependency_sidecar_decode_failure_raises(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").write_bytes(b"Lib \x81\n")

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency is None


def test_load_dependency_sidecar_decode_failure_non_strict_skips(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").write_bytes(b"Lib \x81\n")
    _write(tmp_path, "Ok.s", _CODE)

    project = _load(tmp_path, targets=("Ok", "Main"), strict=False)

    assert "main" not in project
    skipped = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.LOAD_SKIPPED]
    assert [d.program for d in skipped] == ["Main"]
    assert "unable to read dependency file" in skipped[0].detail


def test_load_graphics_decode_failure_strict_raises(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.g").write_bytes(b"\x81 graphics\n")

    with pytest.raises(ArtifactLoadError):
        _load(tmp_path)


def test_load_graphics_decode_failure_non_strict_skips(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.g").write_bytes(b"\x81 graphics\n")

    project = _load(tmp_path, strict=False)

    assert "main" not in project


def test_load_dependency_graphics_decode_failure_raises_dependency_parse_error(tmp_path: Path) -> None:
    _write(tmp_path, "Main.l", "Lib\n")
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Lib.s", _CODE)
    (tmp_path / "Lib.g").write_bytes(b"\x81 graphics\n")

    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)

    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency == "Lib"


def test_load_survives_a_cache_write_failure(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)

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
    _write(consumer, "Main.s", _CODE)
    _write(consumer, "Lib.s", _CODE)
    other.mkdir()
    _write(other, "Lib.l", "OtherSide\n")
    _write(other, "OtherSide.s", _CODE)

    project = SattLineProject.load([consumer, other], LoadMode.DRAFT, ["Main", "Lib"])

    program = project.get("Lib")
    assert program.dependencies == ()
    assert program.deps_path is None
    assert program.sidecar is SidecarState.ABSENT
    stray = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.SIDECAR_ELSEWHERE]
    assert [d.path for d in stray] == [other / "Lib.l"]


def test_missing_sidecar_is_reported_not_invented(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)

    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"])

    program = project.get("Main")
    assert program.dependencies == ()
    assert program.deps_path is None
    assert program.sidecar is SidecarState.ABSENT
    diagnostics = project.diagnostics()
    assert [d.kind for d in diagnostics] == [LoadDiagnosticKind.SIDECAR_MISSING]


def test_empty_sidecar_is_distinct_from_absent(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").write_text("\n\n", encoding="cp1252")

    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"])

    program = project.get("Main")
    assert program.sidecar is SidecarState.EMPTY
    assert program.dependencies == ()
    assert [d.kind for d in project.diagnostics()] == [LoadDiagnosticKind.SIDECAR_EMPTY]


def test_dependency_cycle_is_rejected_before_the_graph_is_returned(tmp_path: Path) -> None:
    _write(tmp_path, "A.s", _CODE)
    _write(tmp_path, "A.l", "B\n")
    _write(tmp_path, "B.s", _CODE)
    _write(tmp_path, "B.l", "A\n")

    with pytest.raises(DependencyCycleError) as excinfo:
        SattLineProject.load([tmp_path], LoadMode.DRAFT, ["A"])

    assert excinfo.value.cycle == ("a", "b", "a")


def test_first_body_match_wins_not_the_newest_datecode(tmp_path: Path) -> None:
    """LIB-01/DATE-01: the first matching body prefix wins.

    A later root with a much larger DateCode must not be preferred; a loader
    that "picks the newest" would silently load a different library version.
    """
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first, "Lib.s", _CODE.replace("DateCode_ 1", "DateCode_ 10"))
    _write(first, "Lib.l", "")
    _write(second, "Lib.s", _CODE.replace("DateCode_ 1", "DateCode_ 9999"))
    _write(second, "Lib.l", "")

    project = SattLineProject.load([first, second], LoadMode.DRAFT, ["Lib"])

    program = project.get("Lib")
    assert program.source_path == first / "Lib.s"
    assert program.code.datecode == 10


def test_load_parses_bodies_in_parallel_with_identical_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "Base.s", _CODE)
    _write(tmp_path, "Child.s", _CODE)
    _write(tmp_path, "Child.l", "Base\n")
    _write(tmp_path, "Leaf.s", _CODE)
    _write(tmp_path, "Leaf.l", "Child\n")

    serial = _load(tmp_path, targets=("Leaf",), workers=1)
    dispatched = _record_dispatched(monkeypatch)
    parallel = _load(tmp_path, targets=("Leaf",), workers=3)

    # The parallel load must really use the pool, not fall back to this process.
    assert sorted(Path(path).name for path in dispatched) == ["Base.s", "Child.s", "Leaf.s"]
    assert serial.programs() == parallel.programs()
    assert serial.graph() == parallel.graph()
    assert serial.diagnostics() == parallel.diagnostics()


@pytest.mark.parametrize(
    ("strict", "broken_is_target", "expected"),
    [
        (True, True, ArtifactLoadError),
        (True, False, DependencyParseError),
        (False, True, None),
        (False, False, None),
    ],
)
def test_a_broken_body_fails_or_skips_the_same_way_in_parallel(
    tmp_path: Path,
    strict: bool,
    broken_is_target: bool,
    expected: type[ProjectLoadError] | None,
) -> None:
    _write(tmp_path, "Good.s", _CODE)
    _write(tmp_path, "Good.l", "Broken\n")
    _write(tmp_path, "Target.s", _CODE)
    _write(tmp_path, "Target.l", "Good\n")
    _write(tmp_path, "Broken.s", _BROKEN)

    targets = ("Broken",) if broken_is_target else ("Target",)
    if expected is not None:
        with pytest.raises(expected):
            _load(tmp_path, targets=targets, strict=strict, workers=3)
        return

    project = _load(tmp_path, targets=targets, strict=strict, workers=3)
    skipped = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.LOAD_SKIPPED]
    assert skipped
    assert "failed to parse" in skipped[0].detail


def test_parallel_parse_falls_back_when_a_pool_cannot_be_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "Lib.s", _CODE)
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib\n")

    def unavailable(max_workers: int) -> object:
        raise OSError(f"cannot start {max_workers} workers here")

    monkeypatch.setattr(project_loader, "_process_pool", unavailable)
    project = _load(tmp_path, workers=2)

    assert tuple(project.programs()) == ("lib", "main")
    assert not [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.LOAD_SKIPPED]


def test_parse_code_file_reads_and_writes_the_ast_cache(tmp_path: Path) -> None:
    code = _write(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    task = (str(code), LoadMode.DRAFT.value, str(cache_dir))

    first = project_loader._parse_code_file(task)
    second = project_loader._parse_code_file(task)

    assert first.ast is not None and first.failure is None
    assert second.ast is not None and second.failure is None
    assert second.ast == first.ast
    assert any(cache_dir.rglob("*"))


def test_parse_code_file_reports_a_parse_failure_as_text(tmp_path: Path) -> None:
    code = _write(tmp_path, "Broken.s", _BROKEN)

    outcome = project_loader._parse_code_file((str(code), LoadMode.DRAFT.value, None))

    assert outcome.ast is None
    assert outcome.failure


def test_parse_code_file_ignores_a_cache_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = _write(tmp_path, "Cached.s", _CODE)

    def failing_save(self: object, code_path: Path, mode: str, ast: BasePicture) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(project_loader.FileASTCache, "save", failing_save)
    outcome = project_loader._parse_code_file((str(code), LoadMode.DRAFT.value, str(tmp_path / "cache")))

    assert outcome.ast is not None


def test_structural_error_during_assembly_still_fails_a_lenient_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cycle is structural: no strictness setting may downgrade it to a skip."""
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.g", _GFX)

    def structural(*args: object, **kwargs: object) -> object:
        raise DependencyCycleError(("main", "main"))

    monkeypatch.setattr(project_loader.ProjectLoader, "_load_companion", structural)
    with pytest.raises(DependencyCycleError):
        _load(tmp_path, strict=False)


@pytest.mark.parametrize("workers", [1, 3])
def test_a_shared_dependency_is_parsed_once(tmp_path: Path, workers: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """A diamond parses the shared body once, whatever the worker count."""
    _write(tmp_path, "Base.s", _CODE)
    _write(tmp_path, "Left.s", _CODE)
    _write(tmp_path, "Left.l", "Base\n")
    _write(tmp_path, "Right.s", _CODE)
    # Same identity as Left's dependency, spelled differently.
    _write(tmp_path, "Right.l", "base\n")
    _write(tmp_path, "Top.s", _CODE)
    _write(tmp_path, "Top.l", "Left\nRight\n")

    dispatched = _record_dispatched(monkeypatch) if workers > 1 else []
    project = _load(tmp_path, targets=("Top",), workers=workers)

    assert tuple(project.programs()) == ("base", "left", "right", "top")
    if workers > 1:
        names = sorted(Path(path).name for path in dispatched)
        assert names == ["Base.s", "Left.s", "Right.s", "Top.s"]


@pytest.mark.parametrize(
    ("methods", "threaded", "expected"),
    [
        (["fork", "spawn", "forkserver"], False, "fork"),
        (["fork", "spawn", "forkserver"], True, "forkserver"),
        (["fork", "spawn"], True, "spawn"),
        (["fork"], True, "fork"),
        ([], False, None),
    ],
)
def test_start_method_never_forks_a_threaded_process(methods: list[str], threaded: bool, expected: str | None) -> None:
    assert project_loader._start_method(methods, threaded=threaded) == expected


def test_a_daemonic_parent_parses_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "Lib.s", _CODE)
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib\n")

    def daemonic() -> object:
        return SimpleNamespace(daemon=True)

    monkeypatch.setattr(project_loader.multiprocessing, "current_process", daemonic)
    events: list[str] = []
    project = _load(tmp_path, workers=2, debug=events)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("daemonic" in event for event in events)


def test_parse_code_file_returns_a_cached_body_without_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = _write(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    FileASTCache(cache_dir).save(code, LoadMode.DRAFT.value, parse_source_file(code))

    def no_parse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a cached body must not be parsed again")

    monkeypatch.setattr(project_loader, "parse_source_file", no_parse)
    outcome = project_loader._parse_code_file((str(code), LoadMode.DRAFT.value, str(cache_dir)))

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


def test_a_dead_worker_pool_falls_back_to_this_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "Lib.s", _CODE)
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib\n")

    monkeypatch.setattr(project_loader, "_process_pool", _failing_pool)
    events: list[str] = []
    project = _load(tmp_path, workers=2, debug=events)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("pool failed" in event.lower() for event in events)


def test_a_cache_write_failure_does_not_fail_a_parallel_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "Lib.s", _CODE)
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib\n")

    def failing_save(self: object, code_path: Path, mode: str, ast: BasePicture) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(project_loader.FileASTCache, "save", failing_save)
    events: list[str] = []
    project = _load(tmp_path, workers=2, cache_dir=tmp_path / "cache", debug=events)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("cache write failed" in event.lower() for event in events)


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
    _write(tmp_path, "Lib.s", _CODE)
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Lib\n")

    _SHUTDOWNS.clear()
    monkeypatch.setattr(project_loader, "_process_pool", _interrupted_pool)

    with pytest.raises(KeyboardInterrupt):
        _load(tmp_path, workers=2)

    assert _SHUTDOWNS == [{"wait": False, "cancel_futures": True}]


def test_a_loader_resolves_one_load(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    loader = project_loader.ProjectLoader(
        roots=[tmp_path],
        mode=LoadMode.DRAFT,
        strict=True,
        debug=None,
        cache_dir=None,
    )
    assert tuple(loader.resolve(["Main"])) == ("main",)

    with pytest.raises(RuntimeError, match="construct another loader"):
        loader.resolve(["Main"])
