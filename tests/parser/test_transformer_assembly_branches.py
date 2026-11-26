"""Branch coverage for the assembly, layout, expression, and shared mixins.

Each test drives one defensive branch that a valid source tree cannot reach, so
the branch is exercised through a synthetic tree or payload rather than through
a corpus fixture.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from lark import Token, Tree
from lark.tree import Meta

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import MappingSource, ModuleTypeDef, ModuleTypeInstance, SourceSpan
from sattline_parser.models.expressions import VarRef
from sattline_parser.models.tails import VarTail
from sattline_parser.transformer._module_shared import (
    GLOBAL_KEYWORD,
    CoordTail,
    InterimCoords,
    submodule_children,
)
from sattline_parser.transformer._payloads import ClipValue, CoordinateClipping

from ._parser_core_test_support import _ExpressionsHarness, _module_header, _ModulesHarness


def _interim_coords(raw: object) -> InterimCoords:
    """Build an ``InterimCoords`` whose coordinate payload is deliberately misshapen."""
    return InterimCoords(coords=cast(Any, raw))


def test_base_picture_module_ignores_an_unknown_tree_tag() -> None:
    mixin = _ModulesHarness()
    header = _module_header("Picture")

    picture = mixin.base_picture_module([header, Tree("unknown_tag", [])])

    assert picture.header is header
    assert picture.position == header.invoke_coord
    assert picture.datatype_defs == []
    assert picture.moduletype_defs == []


def test_invocation_new_module_ignores_an_unknown_tree_tag() -> None:
    mixin = _ModulesHarness()
    header = _module_header("Child")

    module = mixin.invocation_new_module([header, Tree("unknown_tag", [])])

    assert module.header is header
    assert module.submodules == []
    assert module.parametermappings == []


def test_variable_name_skips_unknown_tokens_and_non_text_children() -> None:
    mixin = _ModulesHarness()
    meta = SimpleNamespace(line=2, column=3, start_pos=4, end_pos=9)

    ref = mixin.variable_name(
        meta,
        [
            "Sensor",
            Token(const.KEY_DOT, "."),
            Token("UNKNOWN_TOKEN", "?"),
            42,
            "Value",
        ],
    )

    assert ref.name == "Sensor.Value"
    assert ref.state is None
    assert ref.span == SourceSpan(start=4, end=9, line=2, column=3)


def test_moduletype_definition_ignores_an_unknown_tree_tag() -> None:
    mixin = _ModulesHarness()

    moduletype = mixin.moduletype_definition(Meta(), ["TypeName", Tree("unknown_tag", [])])

    assert moduletype.name == "TypeName"
    assert moduletype.submodules == []
    assert moduletype.moduledef is None


def test_moduletype_definitions_skips_a_non_moduletype_child() -> None:
    mixin = _ModulesHarness()
    real = ModuleTypeDef(name="RealType")

    definitions = mixin.moduletype_definitions([Tree(const.TREE_TAG_MODULETYPE_DEFINITION, [real, "not-a-moduletype"])])

    assert definitions.data == const.TREE_TAG_MODULETYPE_LIST
    assert definitions.children == [real]


def test_moduletype_par_transfer_without_a_source_item() -> None:
    mixin = _ModulesHarness()

    mapping = mixin.moduletype_par_transfer(Meta(), [VarRef("Target")])

    assert mapping.target == VarRef("Target")
    assert mapping.source is None
    assert mapping.source_literal is None
    assert mapping.source_type is MappingSource.VALUE
    assert mapping.is_source_global is False
    assert mapping.is_duration is False

    global_mapping = mixin.moduletype_par_transfer(Meta(), [VarRef("Target"), GLOBAL_KEYWORD])

    assert global_mapping.is_source_global is True
    assert global_mapping.source is None


def test_opt_var_init_rejects_a_tuple_that_is_not_a_pair() -> None:
    mixin = _ModulesHarness()

    assert mixin.opt_var_init([None, (1, 2, 3)]) == ((1, 2, 3), False)


def test_time_value_skips_a_non_text_item_before_any_string() -> None:
    mixin = _ModulesHarness()

    assert mixin.time_value([42]) == {const.GRAMMAR_VALUE_TIME_VALUE: None}
    assert mixin.time_value([42, "1h"]) == {const.GRAMMAR_VALUE_TIME_VALUE: "1h"}


def test_record_keeps_the_first_name_and_description() -> None:
    mixin = _ModulesHarness()

    record = mixin.record(Meta(), ["RecordName", "Description", "ExtraText"])

    assert record.name == "RecordName"
    assert record.description == "Description"


def test_record_ignores_a_tree_that_is_not_a_var_list() -> None:
    mixin = _ModulesHarness()

    record = mixin.record(Meta(), ["RecordName", Tree("unknown_tag", [])])

    assert record.name == "RecordName"
    assert record.var_list == []


def test_coordinates_ignore_an_item_that_is_not_a_coordinate() -> None:
    mixin = _ModulesHarness()

    coords = mixin.coordinates([1.0, "not-a-coordinate", 2.0])

    assert coords.coords == (1.0, 2.0)
    assert coords.tails is None


def test_coordinate_groups_ignore_tails_that_precede_every_value() -> None:
    mixin = _ModulesHarness()
    tail = VarTail("in", "Tail")

    coords = mixin.coordinates([CoordTail(tail), CoordinateClipping((ClipValue(0.5),)), 1.0, 2.0])

    assert coords.coords == (1.0, 2.0)
    assert coords.tails == [tail]
    assert coords.coord_tails == ((), ())


def test_origo_size_pair_skips_an_incomplete_coordinate_payload() -> None:
    mixin = _ModulesHarness()

    pair = mixin.origo_size_pair(
        [
            _interim_coords((1.0,)),
            InterimCoords(coords=(1.0, 2.0)),
            InterimCoords(coords=(3.0, 4.0)),
        ]
    )

    assert pair.coords == ((1.0, 2.0), (3.0, 4.0))
    assert pair.tails is None


def test_coord_invar_tail_keeps_the_first_value() -> None:
    mixin = _ModulesHarness()

    result = mixin.coord_invar_tail(Meta(), ["First", "Second"])

    assert result == CoordTail("First")


def test_clip_value_rejects_a_non_empty_run_without_a_clip_value() -> None:
    mixin = _ModulesHarness()

    with pytest.raises(ValueError, match="clip_value expected a clip value payload"):
        mixin.clip_value(["not-a-clip-value"])


def test_moduledef_ignores_a_list_that_is_not_a_graphics_payload() -> None:
    mixin = _ModulesHarness()

    module_def = mixin.moduledef(Meta(), [["not-a-graph-or-interact-object"]])

    assert module_def.graph_objects == []
    assert module_def.interact_objects == []


def test_bound_tail_keeps_the_first_bound_value() -> None:
    mixin = _ExpressionsHarness()

    result = mixin.invar(Meta(), ["First", "Second"])

    assert result == VarTail("in", "First")


def test_litstring_tail_skips_a_non_text_item() -> None:
    mixin = _ExpressionsHarness()

    result = mixin.litstring_tail(Meta(), [Token("LITSTRING", "LitString"), "Symbol", 42])

    assert result.keyword == "LitString"
    assert result.text == "Symbol"


def test_if_statement_reads_an_unterminated_then_body() -> None:
    mixin = _ExpressionsHarness()

    stmt = mixin.if_statement(
        Meta(),
        [
            Token(const.GRAMMAR_VALUE_IF, "IF"),
            "cond",
            Token(const.GRAMMAR_VALUE_THEN, "THEN"),
            "statement",
        ],
    )

    assert stmt.branches == (("cond", ("statement",)),)
    assert stmt.else_block is None


def test_if_statement_skips_a_token_inside_a_then_body() -> None:
    mixin = _ExpressionsHarness()

    stmt = mixin.if_statement(
        Meta(),
        [
            Token(const.GRAMMAR_VALUE_IF, "IF"),
            "cond",
            Token(const.GRAMMAR_VALUE_THEN, "THEN"),
            Token("UNKNOWN_TOKEN", "?"),
            Token(const.GRAMMAR_VALUE_ENDIF, "ENDIF"),
        ],
    )

    assert stmt.branches == (("cond", ()),)
    assert stmt.else_block is None


def test_if_statement_reads_an_unterminated_else_body() -> None:
    mixin = _ExpressionsHarness()

    stmt = mixin.if_statement(
        Meta(),
        [
            Token(const.GRAMMAR_VALUE_ELSE, "ELSE"),
            "statement",
        ],
    )

    assert stmt.branches == ()
    assert stmt.else_block == ("statement",)


def test_if_statement_skips_a_token_inside_an_else_body() -> None:
    mixin = _ExpressionsHarness()

    stmt = mixin.if_statement(
        Meta(),
        [
            Token(const.GRAMMAR_VALUE_ELSE, "ELSE"),
            Token("UNKNOWN_TOKEN", "?"),
            Token(const.GRAMMAR_VALUE_ENDIF, "ENDIF"),
        ],
    )

    assert stmt.branches == ()
    assert stmt.else_block == ()


def test_module_header_keeps_the_first_name_and_rejects_a_misshapen_coord() -> None:
    mixin = _ModulesHarness()

    header = mixin.module_header(
        Meta(),
        [
            "First",
            "Second",
            InterimCoords(coords=(0.0, 0.0, 0.0, 1.0, 1.0)),
            _interim_coords((1.0,)),
        ],
    )

    assert header.name == "First"
    assert header.invoke_coord == (0.0, 0.0, 0.0, 1.0, 1.0)


def test_submodule_children_ignores_a_child_that_is_not_a_module() -> None:
    instance = ModuleTypeInstance(header=_module_header("Nested"), moduletype_name="NestedType")

    result = submodule_children(["not-a-module", [instance]])

    assert result == [instance]
