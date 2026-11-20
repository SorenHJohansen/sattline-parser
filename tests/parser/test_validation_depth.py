"""Validation rejects a tree deeper than the parser would ever produce.

``validate_basepicture`` runs recursive expression and statement rules. Parsed
input is capped by ``MAX_SOURCE_DEPTH``, but a hand-built or mutated tree is not,
and it used to reach the recursive rules and raise a bare ``RecursionError``. The
entry point now rejects such a tree with the documented nesting error.
"""

from __future__ import annotations

import pytest

from sattline_parser import MAX_SOURCE_DEPTH, SourceTooDeepError, parse_source_text
from sattline_parser.ast import Assignment, BinOp, VarRef
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.validator import MAX_VALIDATED_DEPTH

_PROGRAM = (
    '"Syntax version 2.23"\n'
    '"Original file date: ---"\n'
    '"Program date: ---, name: Deep"\n'
    "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
    "LOCALVARIABLES\n"
    "   A: integer := 0;\n"
    "   R: integer := 0;\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ModuleCode\n"
    "   EQUATIONBLOCK E COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
    "      R = A;\n"
    "ENDDEF (*BasePicture*);\n"
)


def _picture_with_expression_depth(depth: int):
    picture = parse_source_text(_PROGRAM, log_failures=False)
    assert picture.modulecode is not None
    equations = picture.modulecode.equationblocks
    assert equations is not None
    expression: object = VarRef("A")
    for _ in range(depth):
        expression = BinOp(expression, "+", VarRef("A"))
    equations[0].code[0] = Assignment(VarRef("R"), expression)
    return picture


def test_the_validation_bound_matches_the_parser_bound() -> None:
    assert MAX_VALIDATED_DEPTH == MAX_SOURCE_DEPTH


def test_a_manual_tree_below_the_bound_validates() -> None:
    picture = _picture_with_expression_depth(200)

    assert isinstance(validate_basepicture(picture), tuple)


@pytest.mark.parametrize("depth", [300, 1200])
def test_a_manual_tree_past_the_bound_raises_the_documented_error(depth: int) -> None:
    picture = _picture_with_expression_depth(depth)

    with pytest.raises(SourceTooDeepError) as exc_info:
        validate_basepicture(picture)

    assert exc_info.value.limit == MAX_VALIDATED_DEPTH
    assert "nested too deeply" in str(exc_info.value)
