# pyright: reportPrivateUsage=false
"""Unit tests for the project-layer domain skeleton.

Covers the ``sattline_parser.project`` value types, the registry contract, the
DependencyGraph, and the structured load errors. ``SattLineProject.load`` is
wired end to end in Phase 3; the recursive resolution behavior itself lives in
``tests/project/test_loader.py``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import pytest

from sattline_parser import parse_source_text
from sattline_parser.models.ast_model import BasePicture, GraphicsBinding, SourceSpan
from sattline_parser.project import (
    ArtifactLoadError,
    DependencyGraph,
    DependencyNotFoundError,
    DependencyParseError,
    GraphicsCompositeRecord,
    GraphicsMessage,
    GraphicsModel,
    GraphicsPictureDisplayPathRow,
    GraphicsPictureDisplayRecord,
    LoadMode,
    ProgramFormat,
    ProjectLoadError,
    SattLineProgram,
    SattLineProject,
)

_SMALL_PROGRAM = (
    '"SyntaxVersion"\n'
    '"OriginalFileDate"\n'
    '"ProgramDate"\n'
    "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ENDDEF (*BasePicture*);\n"
)


def _code() -> BasePicture:
    return parse_source_text(_SMALL_PROGRAM)


def test_load_mode_members() -> None:
    assert issubclass(LoadMode, Enum)
    assert LoadMode.DRAFT.value == "draft"
    assert LoadMode.OFFICIAL.value == "official"
    assert set(LoadMode) == {LoadMode.DRAFT, LoadMode.OFFICIAL}


def test_program_format_fields() -> None:
    fmt = ProgramFormat(mode=LoadMode.DRAFT, code_ext=".s", graphics_ext=".g", deps_ext=".d")
    assert fmt.mode is LoadMode.DRAFT
    assert (fmt.code_ext, fmt.graphics_ext, fmt.deps_ext) == (".s", ".g", ".d")


def test_program_format_extensions_default_to_none() -> None:
    fmt = ProgramFormat(mode=LoadMode.OFFICIAL)
    assert (fmt.code_ext, fmt.graphics_ext, fmt.deps_ext) == (None, None, None)


def test_graphics_message_fields() -> None:
    msg = GraphicsMessage(severity="warning", message="composite label unknown", line=3, column=5)
    assert msg.severity == "warning"
    assert msg.message == "composite label unknown"
    assert (msg.line, msg.column, msg.length) == (3, 5, 1)


def test_graphics_composite_record_fields() -> None:
    rec = GraphicsCompositeRecord(record_index=2, record_start_line=3, record_end_line=5, family_code="9030")
    assert rec.record_index == 2
    assert (rec.record_start_line, rec.record_end_line) == (3, 5)
    assert rec.family_code == "9030"


def test_graphics_picture_display_path_row_fields() -> None:
    span = SourceSpan(start=0, end=5, line=1, column=1)
    row = GraphicsPictureDisplayPathRow(
        record_index=0, index_token="1", index_value=1, kind="literal", raw_text="PICT", span=span
    )
    assert row.kind == "literal"
    assert (row.index_token, row.index_value) == ("1", 1)
    assert row.raw_text == "PICT"
    assert row.span is span


def test_graphics_picture_display_record_fields() -> None:
    span = SourceSpan(start=6, end=8, line=2, column=2)
    row = GraphicsPictureDisplayPathRow(
        record_index=0, index_token="K", index_value=None, kind="variable", raw_text="K", span=span
    )
    rec = GraphicsPictureDisplayRecord(
        record_index=0,
        record_start_line=1,
        record_end_line=4,
        subtype="2",
        path_row_lines=(2, 3),
        path_rows=(row,),
    )
    assert rec.subtype == "2"
    assert rec.path_row_lines == (2, 3)
    assert rec.path_rows == (row,)


def test_graphics_picture_display_record_defaults() -> None:
    rec = GraphicsPictureDisplayRecord(record_index=0, record_start_line=1, record_end_line=4)
    assert rec.subtype == "2"
    assert rec.path_row_lines == ()
    assert rec.path_rows == ()


def test_graphics_model_holds_parse_result() -> None:
    binding = GraphicsBinding(kind="DspPicturePictureDisplay", raw_text="DspPicturePICT", value=None)
    message = GraphicsMessage(severity="error", message="unable to resolve", line=1, column=1)
    composite = GraphicsCompositeRecord(record_index=0, record_start_line=1, record_end_line=2, family_code="9030")
    display = GraphicsPictureDisplayRecord(record_index=0, record_start_line=1, record_end_line=4)
    model = GraphicsModel(
        bindings=(binding,),
        messages=(message,),
        composite_records=(composite,),
        picture_display_records=(display,),
    )
    assert model.bindings == (binding,)
    assert model.messages == (message,)
    assert model.composite_records == (composite,)
    assert model.picture_display_records == (display,)


def test_graphics_model_defaults() -> None:
    model = GraphicsModel()
    assert model.bindings == ()
    assert model.messages == ()
    assert model.composite_records == ()
    assert model.picture_display_records == ()


def test_sattline_program_defaults() -> None:
    program = SattLineProgram(name="p1", code=_code())
    assert program.graphics is None
    assert program.dependencies == ()
    assert program.format.mode is LoadMode.OFFICIAL


def test_sattline_program_fully_specified() -> None:
    code = _code()
    model = GraphicsModel()
    fmt = ProgramFormat(mode=LoadMode.DRAFT, code_ext=".s", graphics_ext=".g", deps_ext=".d")
    program = SattLineProgram(name="p1", code=code, graphics=model, dependencies=("p2", "P3"), format=fmt)
    assert program.code is code
    assert program.graphics is model
    assert program.dependencies == ("p2", "P3")
    assert program.format is fmt


def test_project_get_contains_programs_case_insensitive() -> None:
    project = SattLineProject._from_programs({"P1": SattLineProgram(name="P1", code=_code())})
    assert "P1" in project
    assert "p1" in project
    assert "nope" not in project
    assert project.get("p1").name == "P1"
    assert list(project.programs()) == ["p1"]
    assert project.programs()["p1"].name == "P1"


def test_project_get_missing_raises_key_error() -> None:
    project = SattLineProject()
    with pytest.raises(KeyError, match="no loaded program"):
        project.get("missing")


def test_project_dependencies_and_dependents() -> None:
    a = SattLineProgram(name="A", code=_code(), dependencies=("B",))
    b = SattLineProgram(name="B", code=_code())
    project = SattLineProject._from_programs({"A": a, "B": b})
    assert project.dependencies_of("A") == ("B",)
    assert project.dependencies_of("a") == ("B",)
    assert project.dependents_of("b") == ("a",)
    assert project.dependents_of("A") == ()


def test_project_graph_derives_nodes_and_edges() -> None:
    a = SattLineProgram(name="A", code=_code(), dependencies=("B",))
    b = SattLineProgram(name="B", code=_code())
    c = SattLineProgram(name="C", code=_code())
    project = SattLineProject._from_programs({"A": a, "B": b, "C": c})
    graph = project.graph()
    assert graph.nodes == ("a", "b", "c")
    assert graph.edges == (("a", "b"),)
    assert graph.dependencies_of("A") == ("b",)
    assert graph.dependencies_of("C") == ()
    assert graph.dependents_of("B") == ("a",)
    assert graph.dependents_of("A") == ()


def test_dependency_graph_standalone() -> None:
    graph = DependencyGraph(nodes=("a", "b"), edges=(("a", "b"),))
    assert graph.nodes == ("a", "b")
    assert graph.dependencies_of("other") == ()
    assert graph.dependents_of("other") == ()


def _write(root: Path, rel: str, content: str = "") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_project_load_wires_discovery_and_dependencies(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _SMALL_PROGRAM)
    _write(tmp_path, "Main.l", "Lib\n")
    _write(tmp_path, "Lib.s", _SMALL_PROGRAM)
    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"])
    assert project.get("Main").dependencies == ("Lib",)
    assert project.get("Lib").name == "Lib"
    assert project.graph().edges == (("main", "lib"),)


def test_project_load_accepts_cache_dir(tmp_path: Path) -> None:
    _write(tmp_path, "Main.s", _SMALL_PROGRAM)
    cache_dir = tmp_path / "cache"
    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"], cache_dir=cache_dir)
    assert project.get("Main").name == "Main"
    assert cache_dir.exists()


def test_project_load_error_surfaces_program_and_message() -> None:
    error = ProjectLoadError(program="P1", message="boom")
    assert error.program == "P1"
    assert error.dependency is None
    assert str(error) == "P1: boom"


def test_project_load_error_surfaces_dependency() -> None:
    error = ProjectLoadError(program="P1", message="boom", dependency="D")
    assert error.dependency == "D"
    assert str(error) == "P1: boom (dependency 'D')"


def test_project_load_error_subclasses() -> None:
    assert issubclass(DependencyNotFoundError, ProjectLoadError)
    assert issubclass(DependencyParseError, ProjectLoadError)
    assert issubclass(ArtifactLoadError, ProjectLoadError)
    assert DependencyNotFoundError("P", "not found", dependency="D").program == "P"
    assert DependencyParseError("P", "bad").dependency is None
    assert ArtifactLoadError("P", "missing .g").program == "P"
