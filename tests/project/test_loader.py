# pyright: reportPrivateUsage=false
"""Unit tests for Phase 3 recursive program loading (``project/loader.py``)."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.api import parse_source_file
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.project import (
    ArtifactLoadError,
    DependencyNotFoundError,
    DependencyParseError,
    LoadMode,
    SattLineProject,
    read_dependency_names,
)
from sattline_parser.project import loader as project_loader

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
    )


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


def test_load_cycle_is_edge_not_error(tmp_path: Path) -> None:
    _write(tmp_path, "A.s", _CODE)
    _write(tmp_path, "A.l", "B\n")
    _write(tmp_path, "B.s", _CODE)
    _write(tmp_path, "B.l", "A\n")
    project = _load(tmp_path, targets=("A",))
    assert len(project.programs()) == 2
    assert project.dependencies_of("A") == ("B",)
    assert project.dependencies_of("B") == ("A",)
    assert set(project.graph().edges) == {("a", "b"), ("b", "a")}


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


def test_load_strict_false_skips_broken_code(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.l", "Broken\n")
    _write(tmp_path, "Broken.s", _BROKEN)
    _write(tmp_path, "Ok.s", _CODE)
    project = _load(tmp_path, targets=("Ok", "Main"), strict=False)
    assert "ok" in project and "main" in project
    assert "broken" not in project


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
    assert program.graphics.picture_display_records == ()
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
    [record] = program.graphics.picture_display_records
    assert record.path_row_lines == (9, 10, 11)


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


def test_load_graphics_structural_errors_do_not_fail_load(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _CODE)
    _write(tmp_path, "Main.g", _GFX_UNTERMINATED)

    program = _load(tmp_path).programs()["main"]

    assert program.graphics is not None
    assert program.graphics.errors, "expected at least one structural graphics message"
