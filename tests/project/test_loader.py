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
from sattline_parser.models.ast_model import (
    BasePicture,
)
from sattline_parser.project import (
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
from sattline_parser.project import loader as project_loader
from sattline_parser.project.ast_cache import FileASTCache, source_snapshot
from sattline_parser.project.models import LoadDiagnosticKind, SidecarState

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


def test_load_resolves_dependencies_across_roots(tmp_path: Path) -> None:
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

    assert project.dependencies_of("Client") == ("LibA",)
    assert project.dependencies_of("LibA") == ("LibB",)
    assert project.dependencies_of("LibB") == ("LibrarySide",)
    assert project.dependencies_of("LibrarySide") == ()


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


def test_load_unreadable_deps_file_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.l").mkdir(exist_ok=True)
    with pytest.raises(DependencyParseError) as exc_info:
        _load(tmp_path)
    assert exc_info.value.program == "Main"
    assert exc_info.value.dependency is None


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
    with patch.object(project_loader, "parse_source_file", side_effect=_counting_parse(call_count)):
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


# --- Phase 4: graphics companion wiring ----------------------------------------


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

    monkeypatch.setattr(project_loader, "_process_pool", unstartable)
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


def test_load_graphics_decode_failure_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    (tmp_path / "Main.g").write_bytes(b"\x81 graphics\n")

    with pytest.raises(ArtifactLoadError):
        _load(tmp_path)


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    def unavailable(max_workers: int) -> object:
        raise OSError(f"cannot start {max_workers} workers here")

    monkeypatch.setattr(project_loader, "_process_pool", unavailable)
    project = _load(tmp_path, workers=2)

    assert tuple(project.programs()) == ("lib", "main")


def test_parse_code_file_reads_but_never_writes_the_ast_cache(tmp_path: Path) -> None:
    """A worker reads the cache and leaves every write to the parent."""
    code = write_file(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    task = (str(code), LoadMode.DRAFT.value, str(cache_dir))

    first = project_loader._parse_code_file(task)
    second = project_loader._parse_code_file(task)

    assert first.ast is not None and first.failure is None
    assert second.ast is not None and second.failure is None
    assert not first.cached
    assert not second.cached
    assert second.ast == first.ast
    assert list((cache_dir / "file_ast").glob("*.pickle")) == []


def test_parse_code_file_reports_a_parse_failure_as_text(tmp_path: Path) -> None:
    code = write_file(tmp_path, "Broken.s", _BROKEN)

    outcome = project_loader._parse_code_file((str(code), LoadMode.DRAFT.value, None))

    assert outcome.ast is None
    assert outcome.failure


def test_parse_code_file_serves_a_warm_entry_without_reparsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = write_file(tmp_path, "Cached.s", _CODE)
    cache_dir = tmp_path / "cache"
    project_loader.FileASTCache(cache_dir).save(code, LoadMode.DRAFT.value, project_loader.parse_source_file(code))

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("a warm entry must not be reparsed")

    monkeypatch.setattr(project_loader, "parse_source_file", refuse)
    outcome = project_loader._parse_code_file((str(code), LoadMode.DRAFT.value, str(cache_dir)))

    assert outcome.ast is not None
    assert outcome.cached


def test_structural_error_during_assembly_fails_the_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cycle is structural, so assembly fails rather than skipping the program."""
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.g", _GFX)

    def structural(*args: object, **kwargs: object) -> object:
        raise DependencyCycleError(("main", "main"))

    monkeypatch.setattr(project_loader.ProjectLoader, "_load_companion", structural)
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
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    def daemonic() -> object:
        return SimpleNamespace(daemon=True)

    monkeypatch.setattr(project_loader.multiprocessing, "current_process", daemonic)
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
    write_file(tmp_path, "Lib.s", _CODE)
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")

    monkeypatch.setattr(project_loader, "_process_pool", _failing_pool)
    events: list[str] = []
    project = _load(tmp_path, workers=2, debug=events)

    assert tuple(project.programs()) == ("lib", "main")
    assert any("pool failed" in event.lower() for event in events)


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
        snapshot: tuple[int, int] | None = None,
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
    seen: list[tuple[int, int] | None] = []
    real_save = FileASTCache.save

    def recording_save(
        self: FileASTCache,
        code_path: Path,
        mode: str,
        ast: BasePicture,
        *,
        snapshot: tuple[int, int] | None = None,
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
        snapshot: tuple[int, int] | None = None,
    ) -> None:
        saves.append(code_path)

    monkeypatch.setattr(FileASTCache, "save", recording_save)
    project = _load(tmp_path, workers=2, cache_dir=cache_dir)

    assert tuple(project.programs()) == ("lib", "main")
    assert saves == []


def test_a_body_that_changes_during_the_parse_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    def stale_snapshot(_path: Path) -> tuple[int, int]:
        return (0, 0)

    monkeypatch.setattr(project_loader, "source_snapshot", stale_snapshot)

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
    monkeypatch.setattr(project_loader, "_process_pool", _interrupted_pool)

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
    """Two roots, each with its own ``Util`` body, and one consumer per root."""
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


def test_a_same_named_unit_in_two_roots_is_not_served_to_the_other_requester(tmp_path: Path) -> None:
    """Each requester is validated against the body its own lookup resolved."""
    first, second = _two_roots_with_a_shared_unit(tmp_path)

    project = SattLineProject.load([first, second], LoadMode.DRAFT, ["Main1", "Main2"])

    assert set(project.programs()) == {"main1", "main2", "util"}
    # Main1's Util declares SharedType; Main2's does not.
    assert project.get("Main1").diagnostics == ()
    assert [diagnostic.code.value for diagnostic in project.get("Main2").diagnostics] == ["SL-V020"]


@pytest.mark.parametrize("targets", [("Main1", "Main2"), ("Main2", "Main1")])
def test_a_shared_unit_name_conflict_is_reported_whatever_the_target_order(
    tmp_path: Path, targets: tuple[str, str]
) -> None:
    first, second = _two_roots_with_a_shared_unit(tmp_path)

    project = SattLineProject.load([first, second], LoadMode.DRAFT, targets)

    conflicts = [d for d in project.diagnostics() if d.kind is LoadDiagnosticKind.NAME_RESOLUTION_CONFLICT]
    assert len(conflicts) == 1
    assert str((first / "Util.s").resolve()) in conflicts[0].detail
    assert str((second / "Util.s").resolve()) in conflicts[0].detail
    # The registry exposes the body the first requester resolved.
    expected_base = first.resolve() if targets[0] == "Main1" else second.resolve()
    assert project.get("Util").resolved_base == expected_base


@pytest.mark.parametrize(
    ("targets", "expected_base"),
    [(("Main2", "Util"), "second"), (("Util", "Main2"), "first")],
)
def test_a_shared_unit_that_is_also_a_target_keeps_the_first_resolution(
    tmp_path: Path, targets: tuple[str, str], expected_base: str
) -> None:
    """The exposed body is the one the first requested target resolved."""
    first, second = _two_roots_with_a_shared_unit(tmp_path)

    project = SattLineProject.load([first, second], LoadMode.DRAFT, targets)

    expected = first if expected_base == "first" else second
    assert project.get("Util").resolved_base == expected.resolve()


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

    assert project_loader._plan_key(Path("/missing/Prog.s")) == str(Path("/missing/Prog.s"))


def test_a_structural_error_escapes_the_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "Main.s", _CODE)

    def _raise(*_args: object, **_kwargs: object) -> object:
        raise StructuralProjectError("Main", "structural")

    monkeypatch.setattr(project_loader.ProjectLoader, "_resolve_artifact", _raise)

    with pytest.raises(StructuralProjectError, match="structural"):
        _load(tmp_path)
