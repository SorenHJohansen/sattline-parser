"""Nested ``ClippingBounds`` annotations survive a format pass.

The annotation attaches to one coordinate value, so its numbers are not part of
the coordinate run and a formatter that only wrote the coordinate tails dropped
them. These tests assert the emitted text, not only tree equality.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import pytest

from sattline_parser.api import parse_source_text
from sattline_parser.ast import BasePicture, NestedClipping, NestedClippingValue, VarTail
from sattline_parser.formatting import UnsupportedFormattingError, format_source
from sattline_parser.grammar import constants as const
from sattline_parser.transformer._graphics_interact_mixin import _coordinate_clipping_groups
from sattline_parser.transformer._module_shared import InterimCoords

_HEADER = """"Syntax version 2.23"
"Original file date: ---"
"Program date: ---, name: Clip"
{invocation} : MODULEDEFINITION DateCode_ 1
"""
_DEFAULT_INVOCATION = "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 )"
_ENDDEF = "ENDDEF (*BasePicture*);\n"
_MODULE_DEF = "ModuleDef\nClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"


def _source(body: str, invocation: str = _DEFAULT_INVOCATION) -> str:
    return _HEADER.format(invocation=invocation) + body + _ENDDEF


def _format(body: str, invocation: str = _DEFAULT_INVOCATION) -> tuple[BasePicture, str]:
    picture = parse_source_text(_source(body, invocation), log_failures=False)
    formatted = format_source(picture)
    reparsed = parse_source_text(formatted, log_failures=False)
    assert reparsed == picture
    return picture, formatted


def test_a_header_coordinate_writes_its_nested_clipping() -> None:
    _, plain = _format(_MODULE_DEF)
    assert plain.count("ClippingBounds =") == 1

    invocation = (
        'BasePicture Invocation ( 3.48 : InVar_ "XVar" ClippingBounds = 3.48 3.48 0.0 '
        ': InVar_ "XMin" 100.0 : InVar_ "XMax" , 1.08 , 0.0 , 0.36 , 0.36 )'
    )
    picture, formatted = _format(_MODULE_DEF, invocation)

    assert picture.header.coordinate_clippings[1:] == ((), (), (), ())
    assert '3.48 : InVar_ "XVar" ClippingBounds = 3.48 3.48 0.0 : InVar_ "XMin" 100.0 : InVar_ "XMax"' in formatted


def test_a_polygon_point_writes_every_nested_clipping_value() -> None:
    line = (
        "   PolygonObject Spline ( 0.0 , 0.0 )\n"
        '      ( 3.04 : InVar_ "XVar" ClippingBounds = 3.04 0.0 : InVar_ "XMin" 100.0 : InVar_ "XMax" , 1.8 )\n'
    )
    picture, formatted = _format(_MODULE_DEF + "GraphObjects :\n" + line)

    assert picture.moduledef is not None
    points = picture.moduledef.graph_objects[0].properties.get(const.KEY_POINTS)
    assert points is not None
    point = points[1]
    assert point.x_clippings == (
        NestedClipping(
            (
                NestedClippingValue(3.04),
                NestedClippingValue(0.0, VarTail("in", "XMin")),
                NestedClippingValue(100.0, VarTail("in", "XMax")),
            )
        ),
    )
    assert point.x_clippings[0].tails == (VarTail("in", "XMin"), VarTail("in", "XMax"))
    assert 'ClippingBounds = 3.04 0.0 : InVar_ "XMin" 100.0 : InVar_ "XMax"' in formatted
    assert '( 3.04 : InVar_ "XVar" ClippingBounds' in formatted


def test_a_plain_nested_clipping_has_no_tails() -> None:
    line = "   PolygonObject ( 0.0 , 0.0 )\n      ( 1.0 ClippingBounds = 1.0 2.0 3.0 , 1.0 )\n"
    picture, formatted = _format(_MODULE_DEF + "GraphObjects :\n" + line)

    assert picture.moduledef is not None
    points = picture.moduledef.graph_objects[0].properties.get(const.KEY_POINTS)
    assert points is not None
    point = points[1]
    assert point.x_clippings[0].values == (
        NestedClippingValue(1.0),
        NestedClippingValue(2.0),
        NestedClippingValue(3.0),
    )
    assert point.x_clippings[0].tails == ()
    assert "ClippingBounds = 1.0 2.0 3.0" in formatted


def test_a_box_object_writes_its_nested_clipping() -> None:
    line = "   RectangleObject ( 1.0 ClippingBounds = 1.0 2.0 , 2.0 ) ( 3.0 , 4.0 )\n"
    _, formatted = _format(_MODULE_DEF + "GraphObjects :\n" + line)

    assert "RectangleObject ( 1.0 ClippingBounds = 1.0 2.0 , 2.0 ) ( 3.0 , 4.0 )" in formatted


def test_a_text_object_writes_its_nested_clipping() -> None:
    line = '   TextObject ( 1.0 ClippingBounds = 1.0 2.0 , 2.0 ) ( 3.0 , 4.0 )\n      "Label"\n'
    picture, formatted = _format(_MODULE_DEF + "GraphObjects :\n" + line)

    assert picture.moduledef is not None
    properties = picture.moduledef.graph_objects[0].properties
    assert const.KEY_COORD_CLIPPINGS in properties
    assert "TextObject ( 1.0 ClippingBounds = 1.0 2.0 , 2.0 ) ( 3.0 , 4.0 )" in formatted


def test_a_segment_writes_its_nested_clipping() -> None:
    line = "   SegmentObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 ) ( 2.0 ClippingBounds = 1.0 2.0 , 2.0 )\n"
    _, formatted = _format(_MODULE_DEF + "GraphObjects :\n" + line)

    assert "SegmentObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 ) ( 2.0 ClippingBounds = 1.0 2.0 , 2.0 )" in formatted


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "   TextBox_ ( 1.0 ClippingBounds = 1.0 2.0 , 0.5 ) ( 1.0 , 1.0 )\n      Bool_Value\n",
            "TextBox_ ( 1.0 ClippingBounds = 1.0 2.0 , 0.5 ) ( 1.0 , 1.0 )",
        ),
        (
            "   ComButProc_ ( 1.0 ClippingBounds = 1.0 2.0 , 0.5 ) ( 1.0 , 1.0 ) Toggle\n",
            "ComButProc_ ( 1.0 ClippingBounds = 1.0 2.0 , 0.5 ) ( 1.0 , 1.0 ) Toggle",
        ),
    ],
)
def test_an_interactor_writes_its_nested_clipping(line: str, expected: str) -> None:
    _, formatted = _format(_MODULE_DEF + "InteractObjects :\n" + line)

    assert expected in formatted


def test_a_clipping_corner_writes_its_nested_clipping() -> None:
    _, formatted = _format("ModuleDef\nClippingBounds = ( 1.0 ClippingBounds = 1.0 2.0 , 2.0 ) ( 3.0 , 4.0 )\n")

    assert "ClippingBounds = ( 1.0 ClippingBounds = 1.0 2.0 , 2.0 ) ( 3.0 , 4.0 )" in formatted


def test_a_tail_written_after_the_annotation_is_refused() -> None:
    invocation = (
        'BasePicture Invocation ( 0.0 ClippingBounds = 1.0 : InVar_ "A" 2.0 : InVar_ "B" '
        ': InVar_ "C" , 1.0 , 1.0 , 1.0 , 1.0 )'
    )
    picture = parse_source_text(_source(_MODULE_DEF, invocation), log_failures=False)
    annotation = picture.header.coordinate_clippings[0][0]
    assert annotation.tails == (VarTail("in", "A"), VarTail("in", "B"))

    with pytest.raises(UnsupportedFormattingError, match="nested ClippingBounds"):
        format_source(picture)


def test_an_unrecorded_clipping_split_yields_no_groups() -> None:
    assert _coordinate_clipping_groups([InterimCoords(coords=(1.0, 2.0))]) == ()
