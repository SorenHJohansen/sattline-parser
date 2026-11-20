"""The project boundary accepts every depth the parser accepts.

``SattLineProject.from_programs`` copies the parsed tree before it freezes it, so
the caller keeps ownership. ``copy.deepcopy`` grows the Python call stack several
frames per level and overflows on a tree the parser accepts; the project layer
therefore copies with an explicit stack. These tests hold the boundary: the whole
accepted depth range attaches, and the parser still rejects the term after it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from sattline_parser import SourceTooDeepError, to_jsonable
from sattline_parser.api import parse_source_text
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.project import LoadMode, SattLineProject
from sattline_parser.project.models import SattLineProgram


def _program(terms: int) -> str:
    chain = " + ".join(["A"] * terms)
    return (
        '"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-08-19-12:00:00.000, name: Deep"\n'
        "BasePicture Invocation\n"
        "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        "    ) : MODULEDEFINITION DateCode_ 1\n"
        "\n"
        "LOCALVARIABLES\n"
        "   A: real  := 1.0;\n"
        "   R: real  := 0.0;\n"
        "\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        f"      R = {chain};\n"
        "\n"
        "ENDDEF (*BasePicture*);\n"
    )


def _parse(terms: int) -> BasePicture:
    return parse_source_text(_program(terms), log_failures=False)


def _attach(picture: BasePicture) -> SattLineProject:
    return SattLineProject.from_programs({"Deep": SattLineProgram(name="Deep", code=picture)})


def _largest_accepted_terms() -> int:
    accepted = 0
    for terms in range(200, 300):
        try:
            _parse(terms)
        except SourceTooDeepError:
            return accepted
        accepted = terms
    return accepted


def test_the_accepted_depth_boundary_is_where_the_parser_says_it_is() -> None:
    accepted = _largest_accepted_terms()

    assert accepted >= 249
    with pytest.raises(SourceTooDeepError):
        _parse(accepted + 1)


@pytest.mark.parametrize("terms", [240, 244])
def test_a_deep_tree_that_deepcopy_could_not_copy_attaches(terms: int) -> None:
    """240 copied, 244 and above overflowed ``copy.deepcopy`` before the fix."""
    picture = _parse(terms)

    project = _attach(picture)

    attached = project.get("Deep")
    # A frozen tree holds tuples where the parsed tree holds lists, so the deep
    # comparison goes through the data view, which emits both as a list.
    assert to_jsonable(attached.code) == to_jsonable(picture)
    assert attached.code is not picture


def test_the_largest_accepted_tree_attaches() -> None:
    accepted = _largest_accepted_terms()

    project = _attach(_parse(accepted))

    assert to_jsonable(project.get("Deep").code) == to_jsonable(_parse(accepted))


def test_the_attached_tree_is_frozen_and_the_callers_tree_is_not() -> None:
    picture = _parse(240)

    project = _attach(picture)

    attached = project.get("Deep").code
    assert isinstance(attached.localvariables, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        attached.name = "Renamed"
    # The caller still owns a mutable tree: lists stayed lists.
    assert isinstance(picture.localvariables, list)
    picture.name = "Renamed"
    assert picture.name == "Renamed"


def test_a_project_load_freezes_the_largest_accepted_tree(tmp_path: Path) -> None:
    """A load freezes in place, so it costs one Python frame per level.

    ``from_programs`` copies iteratively and ``load`` freezes the parsed tree in
    place; both must hold at the depth the parser accepts.
    """
    accepted = _largest_accepted_terms()
    (tmp_path / "Deep.s").write_text(_program(accepted), encoding="cp1252")

    project = SattLineProject.load(roots=[tmp_path], mode=LoadMode.DRAFT, targets=["Deep"])

    attached = project.get("Deep").code
    assert isinstance(attached.localvariables, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        attached.name = "Renamed"
