"""Benchmarks for project loading, planning, validation, and the AST cache."""

from __future__ import annotations

from itertools import count
from pathlib import Path
from typing import Any

import pytest

from sattline_parser.project import LoadMode, SattLineProject

_ROOT_KEYWORD = '"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"\n'


def _body(name: str) -> str:
    """A minimal parseable unit body."""
    return (
        _ROOT_KEYWORD
        + '"Original file date: ---"\n'
        + f'"Program date: 2026-04-23-12:00:00.000, name: {name}"\n\n'
        + """BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""
    )


def _moduletype(name: str, *, instantiates: str | None = None) -> str:
    submodules = (
        ""
        if instantiates is None
        else (
            "   SUBMODULES\n"
            "      Child Invocation\n"
            "         ( 0.0 , 0.0 , 0.0 , 0.4 , 0.4\n"
            f"          ) : {instantiates};\n"
        )
    )
    return (
        f"   {name} = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      Value: integer := 0;\n"
        f"{submodules}"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        f"   ENDDEF (*{name}*);\n"
    )


def _moduletype_chain_source(name: str, depth: int) -> str:
    """One unit with a chain of ``depth`` module types, each using the previous."""
    definitions = ["TYPEDEFINITIONS\n"]
    for index in range(depth):
        previous = None if index == 0 else f"Type{index - 1}"
        definitions.append(_moduletype(f"Type{index}", instantiates=previous))
    return _body(name).replace("ModuleDef\n", "".join(definitions) + "ModuleDef\n", 1)


def _write_unit(root: Path, name: str, *, dependencies: tuple[str, ...] = (), code: str | None = None) -> None:
    (root / f"{name}.s").write_text(code if code is not None else _body(name), encoding="utf-8")
    if dependencies:
        (root / f"{name}.l").write_text("".join(f"{dependency}\n" for dependency in dependencies), encoding="utf-8")


def _load(root: Path, targets: tuple[str, ...], *, cache_dir: Path | None = None) -> SattLineProject:
    return SattLineProject.load([root], mode=LoadMode.DRAFT, targets=targets, cache_dir=cache_dir)


@pytest.fixture(scope="session")
def deep_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, tuple[str, ...]]:
    """A linear dependency chain, the planner's deepest path."""
    root = tmp_path_factory.mktemp("bench-deep")
    depth = 12
    _write_unit(root, "Unit0")
    for index in range(1, depth):
        _write_unit(root, f"Unit{index}", dependencies=(f"Unit{index - 1}",))
    return root, (f"Unit{depth - 1}",)


@pytest.fixture(scope="session")
def wide_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, tuple[str, ...]]:
    """One target with many direct dependencies, the planner's widest frame."""
    root = tmp_path_factory.mktemp("bench-wide")
    width = 40
    names = tuple(f"Lib{index}" for index in range(width))
    for name in names:
        _write_unit(root, name)
    _write_unit(root, "Main", dependencies=names)
    return root, ("Main",)


@pytest.fixture(scope="session")
def diamond_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, tuple[str, ...]]:
    """Overlapping closures: Top reaches Base through both Left and Right."""
    root = tmp_path_factory.mktemp("bench-diamond")
    _write_unit(root, "Base")
    _write_unit(root, "Left", dependencies=("Base",))
    _write_unit(root, "Right", dependencies=("Base",))
    _write_unit(root, "Top", dependencies=("Left", "Right"))
    return root, ("Top",)


@pytest.fixture(scope="session")
def moduletype_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, tuple[str, ...]]:
    """A large acyclic instantiation graph, the cycle check's normal case."""
    root = tmp_path_factory.mktemp("bench-moduletypes")
    _write_unit(root, "Main", code=_moduletype_chain_source("Main", 60))
    return root, ("Main",)


def test_bench_project_load_deep_chain(benchmark: Any, deep_project: tuple[Path, tuple[str, ...]]) -> None:
    root, targets = deep_project
    project = benchmark(lambda: _load(root, targets))
    assert len(project.programs()) == 12


def test_bench_project_load_wide_graph(benchmark: Any, wide_project: tuple[Path, tuple[str, ...]]) -> None:
    root, targets = wide_project
    project = benchmark(lambda: _load(root, targets))
    assert len(project.programs()) == 41


def test_bench_project_load_diamond(benchmark: Any, diamond_project: tuple[Path, tuple[str, ...]]) -> None:
    root, targets = diamond_project
    project = benchmark(lambda: _load(root, targets))
    assert len(project.programs()) == 4


def test_bench_project_load_moduletype_graph(benchmark: Any, moduletype_project: tuple[Path, tuple[str, ...]]) -> None:
    root, targets = moduletype_project
    project = benchmark(lambda: _load(root, targets))
    assert len(project.programs()) == 1


def test_bench_project_load_uncached(benchmark: Any, diamond_project: tuple[Path, tuple[str, ...]]) -> None:
    """The baseline: no cache directory, so no source is hashed."""
    root, targets = diamond_project
    project = benchmark(lambda: _load(root, targets, cache_dir=None))
    assert len(project.programs()) == 4


def test_bench_project_load_cold_ast_cache(
    benchmark: Any, tmp_path: Path, diamond_project: tuple[Path, tuple[str, ...]]
) -> None:
    """Each round starts with an empty AST cache, so it parses and stores."""
    root, targets = diamond_project
    rounds = count()

    def load_cold() -> SattLineProject:
        return _load(root, targets, cache_dir=tmp_path / f"cold-{next(rounds)}")

    project = benchmark(load_cold)
    assert len(project.programs()) == 4


def test_bench_project_load_warm_ast_cache(
    benchmark: Any, tmp_path: Path, diamond_project: tuple[Path, tuple[str, ...]]
) -> None:
    """A primed cache still reads each source to verify the digest."""
    root, targets = diamond_project
    cache_dir = tmp_path / "warm"
    _load(root, targets, cache_dir=cache_dir)
    project = benchmark(lambda: _load(root, targets, cache_dir=cache_dir))
    assert len(project.programs()) == 4
