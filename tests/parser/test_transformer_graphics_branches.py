# pyright: reportPrivateUsage=false, reportTypedDictNotRequiredAccess=false

"""Branch coverage for transformer helpers outside the main happy paths.

Each test calls one transformer method or module helper with synthetic
``Token``, ``Tree``, and model inputs, so the uncovered arm of a condition is
exercised directly. The assertions check the returned payload, not merely that
the line ran.
"""

from __future__ import annotations

from lark import Token, Tree
from lark.tree import Meta

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import CodeComment
from sattline_parser.models.clauses import (
    ColourSpec,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
)
from sattline_parser.transformer._comments_mixin import comment_pieces
from sattline_parser.transformer._module_shared import InterimCoords
from sattline_parser.transformer._sfc_mixin import _seq_control_flags
from sattline_parser.transformer.sl_transformer import _header_description, _header_line_text

from ._parser_core_test_support import _GraphicsHarness, _SFCHarness


def test_text_object_ignores_an_unrelated_tailed_clause() -> None:
    mixin = _GraphicsHarness()

    graph_object = mixin.text_object([TailedClause("Unrelated_", 1)])

    assert graph_object.type == const.GRAMMAR_VALUE_TEXTOBJECT
    assert const.KEY_WIDTH not in graph_object.properties
    assert const.KEY_VALUE_FRACTION not in graph_object.properties
    assert const.KEY_FORMAT_STRING not in graph_object.properties


def test_tailed_clause_keeps_the_first_keyword_token() -> None:
    mixin = _GraphicsHarness()

    clause = mixin._tailed_clause([Token("WIDTH_KEY", "Width_"), Token("WIDTH_KEY", "Width_"), 2])

    assert clause == TailedClause("Width_", 2)


def test_single_clause_skips_a_non_clause_child() -> None:
    mixin = _GraphicsHarness()
    clause = TailedClause("Width_", 4)

    assert mixin._single_clause(["ignored", clause]) is clause


def test_colour_spec_ignores_an_unrelated_clause() -> None:
    mixin = _GraphicsHarness()

    spec = mixin._colour_spec("outline", [TailedClause("Unrelated_", 1)])

    assert spec.kind == "outline"
    assert spec.width is None
    assert spec.style is None
    assert spec.assignments == ()


def test_color_properties_skips_a_non_colour_child() -> None:
    mixin = _GraphicsHarness()
    spec = ColourSpec("fill")

    assert mixin.color_properties(["ignored", spec]) is spec


def test_box_graph_object_without_a_box_has_no_coords() -> None:
    mixin = _GraphicsHarness()

    rectangle = mixin.rectangle_object(["ignored"])

    assert rectangle.type == const.GRAMMAR_VALUE_RECTANGLEOBJECT
    assert rectangle.properties == {}


def test_segment_object_ignores_a_five_value_coordinate() -> None:
    mixin = _GraphicsHarness()

    segment = mixin.segment_object([InterimCoords(coords=(1.0, 2.0, 3.0, 4.0, 5.0))])

    assert segment.type == const.GRAMMAR_VALUE_SEGMENTOBJECT
    assert const.KEY_COORDS not in segment.properties
    assert const.KEY_SEGMENT_POINT not in segment.properties
    assert const.KEY_COORD_TAILS not in segment.properties


def test_combutproc_item_keeps_the_default_type_for_an_unrelated_token() -> None:
    mixin = _GraphicsHarness()

    item = mixin.combutproc_item(Meta(), [Token("UNRELATED", "Something"), ProcedureCall("ToggleWindow")])

    assert item.type == const.GRAMMAR_VALUE_COMBUTPROC
    assert item.properties[const.KEY_PROCEDURE] == ProcedureCall("ToggleWindow")


def test_combutproc_item_ignores_an_unrelated_item() -> None:
    mixin = _GraphicsHarness()

    item = mixin.combutproc_item(Meta(), [InterimCoords(coords=((0.0, 0.0), (1.0, 1.0))), "ignored"])

    assert item.type == const.GRAMMAR_VALUE_COMBUTPROC
    assert item.properties[const.KEY_COORDS] == [((0.0, 0.0), (1.0, 1.0))]


def test_interact_type_simple_skips_a_non_token() -> None:
    mixin = _GraphicsHarness()

    assert mixin.interact_type_simple(["ignored", Token(const.TOKEN_NAME, "Button_")]) == "Button_"


def test_interact_body_skips_a_token() -> None:
    mixin = _GraphicsHarness()

    assert mixin.interact_body([Token("JUNK", "ignored"), "payload"]) == "payload"


def test_interact_simple_item_ignores_an_unhandled_item() -> None:
    mixin = _GraphicsHarness()

    item = mixin.interact_simple_item(Meta(), ["Button_", 5])

    assert item.type == "Button_"
    assert item.properties[const.KEY_COORDS] is None
    assert item.properties[const.KEY_BODY] is None


def test_interact_scale_selector_skips_a_non_token() -> None:
    mixin = _GraphicsHarness()

    selector = mixin.interact_scale_selector(Meta(), ["ignored", Token(const.TOKEN_NAME, const.GRAMMAR_VALUE_ABS)])

    assert selector == ScaleSelector("abs")


def test_interact_pick_button_ignores_a_non_token_non_string() -> None:
    mixin = _GraphicsHarness()

    button = mixin.interact_pick_button(Meta(), [1, "PickVar"])

    assert button == PickButton(value="PickVar", reference=None)


def test_interact_value_line_skips_a_token() -> None:
    mixin = _GraphicsHarness()

    assert mixin.interact_value_line([Token("JUNK", "ignored"), 7]) == 7


def test_seq_control_flags_ignores_an_unknown_spelling() -> None:
    tree = Tree(
        const.KEY_SEQ_CONTROL_OPS,
        [Token("SEQ_CONTROL", "Unknown"), Token("SEQTIMER", const.GRAMMAR_VALUE_SEQTIMER)],
    )

    seqcontrol, seqtimer = _seq_control_flags(tree)

    assert seqcontrol is False
    assert seqtimer is True


def test_seqfork_skips_a_non_string_item() -> None:
    mixin = _SFCHarness()

    fork = mixin.seqfork([Token(const.TOKEN_NAME, "StepA"), 5])

    assert fork.targets == ("StepA",)
    assert fork.has_break is False


def test_sequence_keeps_the_first_layer_and_the_first_two_coordinates() -> None:
    mixin = _SFCHarness()

    sequence = mixin.sequence(
        Meta(),
        [
            "Main",
            7,
            8,
            (0.0, 0.0),
            (1.0, 1.0),
            (2.0, 2.0),
            Tree("unrelated_tree", []),
        ],
    )

    assert sequence.name == "Main"
    assert sequence.layer_info == 7
    assert sequence.position == (0.0, 0.0)
    assert sequence.size == (1.0, 1.0)
    assert sequence.code == []


def test_equationblock_keeps_the_first_layer_and_the_first_two_coordinates() -> None:
    mixin = _SFCHarness()

    equation = mixin.equationblock(Meta(), [3, 4, (0.0, 0.0), (1.0, 1.0), (2.0, 2.0)])

    assert equation.layer_info == 3
    assert equation.position == (0.0, 0.0)
    assert equation.size == (1.0, 1.0)
    assert equation.code == []


def test_comment_pieces_skips_a_non_token_non_tree_child() -> None:
    pieces = comment_pieces(Tree("comment", [42, Token("COMMENT_TEXT", "abc")]))

    assert [str(piece) for piece in pieces] == ["abc"]


def test_header_line_text_skips_a_non_string_child() -> None:
    assert _header_line_text(Tree("syntax_version_line", [42, "line text"])) == "line text"


def test_header_description_skips_a_non_comment_tree_child() -> None:
    description = _header_description(Tree("change_description", [Tree("unrelated", []), Tree("comment", [])]))

    assert isinstance(description, CodeComment)
    assert description.text == ""
