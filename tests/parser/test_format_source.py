"""Round-trip tests for the whole-file formatter (``formatting/source.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sattline_parser.api import parse_source_file, parse_source_text
from sattline_parser.ast import CodeComment, VarTail
from sattline_parser.formatting import UnsupportedFormattingError, format_module, format_source
from sattline_parser.grammar import constants as const

_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"


def _fixtures() -> list[Path]:
    return sorted([*_CORPUS.glob("valid/*.s"), *_CORPUS.glob("edge_cases/*.s")])


@pytest.mark.parametrize("path", _fixtures(), ids=lambda path: path.name)
def test_a_whole_file_round_trips_through_its_own_source(path: Path) -> None:
    picture = parse_source_file(path, log_failures=False)

    formatted = format_source(picture)
    reparsed = parse_source_text(formatted, log_failures=False)

    assert reparsed == picture
    # Formatting is idempotent: a second pass changes nothing.
    assert format_source(reparsed) == formatted


def test_graphics_and_interactor_properties_survive_the_round_trip() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "InteractWidgets.s", log_failures=False)

    reparsed = parse_source_text(format_source(picture), log_failures=False)

    assert reparsed.moduledef is not None
    original_objects = picture.moduledef.interact_objects if picture.moduledef else []
    reparsed_objects = reparsed.moduledef.interact_objects if reparsed.moduledef else []
    assert [obj.properties for obj in reparsed_objects] == [obj.properties for obj in original_objects]


def test_interactor_literal_body_lines_round_trip() -> None:
    picture = parse_source_text(
        """\"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N\"
\"Original file date: ---\"
\"Program date: 2026-04-23-12:00:00.000, name: InteractLiterals\"
BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
InteractObjects :
   TextBox_ ( -0.8 , 0.9 ) ( 0.8 , 0.7 )
      True
      2.5
      \"text\"
      5
ENDDEF (*BasePicture*);
"""
    )

    formatted = format_source(picture)

    assert parse_source_text(formatted) == picture
    assert "\n        True\n" in formatted
    assert "\n        2.5\n" in formatted
    assert '\n        "text"\n' in formatted
    assert "\n        5\n" in formatted


def test_simple_interactor_coordinate_tails_round_trip() -> None:
    picture = parse_source_text(
        """\"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N\"
\"Original file date: ---\"
\"Program date: 2026-04-23-12:00:00.000, name: InteractTail\"
BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
   X: real := 0.0;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
InteractObjects :
   ComBut_ ( 0.0 : InVar_ \"X\" , 0.5 ) ( 1.0 , 1.0 )
      Bool_Value
ENDDEF (*BasePicture*);
"""
    )

    assert picture.moduledef is not None
    interact = picture.moduledef.interact_objects[0]
    tails = interact.properties.get(const.KEY_COORD_TAILS)
    assert tails is not None
    assert tails[0] == (VarTail("in", "X"),)
    assert parse_source_text(format_source(picture)) == picture


def test_segment_coordinate_tails_round_trip() -> None:
    picture = parse_source_text(
        """\"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N\"
\"Original file date: ---\"
\"Program date: 2026-04-23-12:00:00.000, name: SegmentTail\"
BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
   BX: real := 0.0;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   SegmentObject ( 0.0 , 0.0 ) ( 1.0 : InVar_ \"BX\" , 1.0 ) ( 2.0 : InVar_ \"BX\" , 2.0 )
ENDDEF (*BasePicture*);
"""
    )

    assert picture.moduledef is not None
    segment = picture.moduledef.graph_objects[0]
    tails = segment.properties.get(const.KEY_COORD_TAILS)
    assert tails is not None
    assert tails[2] == (VarTail("in", "BX"),)
    assert tails[4] == (VarTail("in", "BX"),)
    assert parse_source_text(format_source(picture)) == picture


def test_format_module_renders_one_block() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "ModuleDefWithCode.s", log_failures=False)
    assert picture.moduledef is not None

    text = format_module(picture.moduledef)

    assert text.startswith("ModuleDef\n")
    assert "ClippingBounds =" in text


def test_a_lost_tail_association_raises_instead_of_moving_the_tail() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "MinimalProgram.s", log_failures=False)
    picture.header.invoke_coord_tails = [VarTail("in", "PosX")]
    picture.header.coordinate_tails = ()

    with pytest.raises(UnsupportedFormattingError, match="coordinate tails"):
        format_source(picture)


def test_a_header_coordinate_tail_is_written_after_its_coordinate() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "UnCompressedFullGrammar.s", log_failures=False)

    formatted = format_source(picture)
    submodule = next(
        submodule for submodule in picture.submodules if any(getattr(submodule.header, "coordinate_tails", ()))
    )
    groups = submodule.header.coordinate_tails
    index = next(position for position, group in enumerate(groups) if group)
    value = str(float(submodule.header.invoke_coord[index]))
    tail = groups[index][0]
    assert isinstance(tail, VarTail)
    line = next(line for line in formatted.splitlines() if line.strip().startswith(submodule.header.name))

    assert f"{value} : {'InVar_' if tail.direction == 'in' else 'OutVar_'}" in line


_ROUND_TRIP_HEADER = """"Syntax version 2.23"
"Original file date: ---"
"Program date: ---, name: RoundTrip"
"""
_ROUND_TRIP_MODULE_DEF = "ModuleDef\nClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"


def _round_trip_source(
    body: str,
    *,
    header: str = "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 )",
    definition_tail: str = "",
) -> str:
    return (
        _ROUND_TRIP_HEADER
        + f"{header} : MODULEDEFINITION DateCode_ 1{definition_tail}\n"
        + body
        + "ENDDEF (*BasePicture*);\n"
    )


def _formatted(source: str) -> str:
    picture = parse_source_text(source, log_failures=False)
    formatted = format_source(picture)
    reparsed = parse_source_text(formatted, log_failures=False)
    assert reparsed == picture
    assert format_source(reparsed) == formatted
    return formatted


def test_a_bare_time_value_initializer_keeps_the_keyword() -> None:
    formatted = _formatted(_round_trip_source("LOCALVARIABLES\n   T: time := Time_Value;\n" + _ROUND_TRIP_MODULE_DEF))

    assert "T: time := Time_Value;" in formatted
    assert '"Time_Value"' not in formatted


def test_a_bare_duration_value_initializer_keeps_the_marker() -> None:
    formatted = _formatted(
        _round_trip_source("LOCALVARIABLES\n   D: duration := Duration_Value;\n" + _ROUND_TRIP_MODULE_DEF)
    )

    assert "D: duration := Duration_Value;" in formatted


def test_an_empty_record_description_is_preserved() -> None:
    formatted = _formatted(
        _round_trip_source('TYPEDEFINITIONS\n   R "" = RECORD DateCode_ 1\n   ENDDEF (*R*);\n' + _ROUND_TRIP_MODULE_DEF)
    )

    assert 'R "" = RECORD' in formatted


def test_an_empty_equation_round_trips_without_an_invented_comment() -> None:
    formatted = _formatted(_round_trip_source(_ROUND_TRIP_MODULE_DEF + "MODULECODE\n   EQUATIONBLOCK :\n"))

    assert "EQUATIONBLOCK :" in formatted
    assert "(* empty *)" not in formatted


def test_two_header_description_comments_keep_their_positions() -> None:
    formatted = _formatted(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF,
            header="BasePicture (* before *) Invocation (* after *) ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 )",
        )
    )

    assert "(* before *) Invocation (* after *)" in formatted


def test_a_single_header_description_comment_is_written_before_invocation() -> None:
    formatted = _formatted(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF,
            header="BasePicture Invocation (* after *) ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 )",
        )
    )

    assert "BasePicture (* after *) Invocation" in formatted


def test_a_root_frame_module_marker_round_trips() -> None:
    formatted = _formatted(_round_trip_source(_ROUND_TRIP_MODULE_DEF, definition_tail=" (Frame_Module)"))

    assert "MODULEDEFINITION DateCode_ 1 (Frame_Module)" in formatted


def test_a_written_default_grid_is_preserved() -> None:
    formatted = _formatted(
        _round_trip_source("ModuleDef\nClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\nGrid = 0.2\n")
    )

    assert "Grid = 0.2" in formatted


def test_a_colour_clause_written_in_upper_case_keeps_its_value() -> None:
    formatted = _formatted(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF
            + "GraphObjects :\n   RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 ) OutlineColour : WIDTH_ = 2 COLOURSTYLE = 1.0\n"
        )
    )

    assert "WIDTH_ = 2" in formatted
    assert "COLOURSTYLE = 1.0" in formatted


def test_a_time_value_mapping_is_written_as_source() -> None:
    formatted = _formatted(
        _round_trip_source(
            'SUBMODULES\n   Child Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : ModType ( P => Time_Value "1h" );\n'
            + _ROUND_TRIP_MODULE_DEF
        )
    )

    assert 'P => Time_Value "1h"' in formatted
    assert "{" not in formatted


def test_a_quoted_duration_value_literal_is_not_read_as_the_keyword() -> None:
    picture = parse_source_text(
        _round_trip_source(
            'SUBMODULES\n   Child Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : ModType ( P => "Duration_Value" );\n'
            + _ROUND_TRIP_MODULE_DEF
        ),
        log_failures=False,
    )
    mapping = picture.submodules[0].parametermappings[0]

    assert mapping.is_duration is False
    assert mapping.source_literal == "Duration_Value"
    assert 'P => "Duration_Value"' in format_source(picture)


def test_a_procedure_interactor_keeps_its_written_keyword() -> None:
    formatted = _formatted(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF
            + "InteractObjects :\n   ProcedureInteract ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n      ToggleWindow 1\n"
        )
    )

    assert "ProcedureInteract" in formatted
    assert "ComButProc_" not in formatted


def test_a_var_name_marker_without_text_is_written_as_an_empty_label() -> None:
    formatted = _formatted(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF + "GraphObjects :\n   TextObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 ) VarName\n"
        )
    )

    assert '"" VarName' in formatted


def test_a_frame_module_mapping_is_written_after_enddef() -> None:
    formatted = _formatted(
        _round_trip_source(
            "SUBMODULES\n"
            "   FrameInst Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION (Frame_Module)\n"
            "   ModuleDef\n"
            "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "   ENDDEF (*FrameInst*) ( P => 1 );\n" + _ROUND_TRIP_MODULE_DEF
        )
    )

    assert "ENDDEF (*FrameInst*) (P => 1);" in formatted


def test_an_interactor_layer_line_keeps_its_keyword() -> None:
    formatted = _formatted(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF + "InteractObjects :\n   TextBox_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n      Layer_ = 2\n"
        )
    )

    assert "\n        Layer_ = 2\n" in formatted


def test_an_interactor_layer_value_is_a_plain_int_not_a_literal() -> None:
    picture = parse_source_text(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF + "InteractObjects :\n   TextBox_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n      Layer_ = 2\n"
        ),
        log_failures=False,
    )

    assert picture.moduledef is not None
    body = picture.moduledef.interact_objects[0].properties.get(const.KEY_BODY)
    assert body is not None
    assert type(body[0]) is int


def test_a_group_connection_keeps_its_state_suffix() -> None:
    formatted = _formatted(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF,
            header="BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 )",
            definition_tail=" (GroupConn = P:Old)",
        )
    )

    assert "(GroupConn = P:Old)" in formatted


def test_a_parameter_mapping_keeps_state_suffixes_on_both_sides() -> None:
    formatted = _formatted(
        _round_trip_source(
            "SUBMODULES\n   Child Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : ModType ( P:Old => Q:New );\n"
            + _ROUND_TRIP_MODULE_DEF
        )
    )

    assert "P:Old => Q:New" in formatted


def test_mixed_colour_blocks_keep_their_written_order() -> None:
    formatted = _formatted(
        _round_trip_source(
            "LOCALVARIABLES\n   A: integer := 0;\n"
            + _ROUND_TRIP_MODULE_DEF
            + "GraphObjects :\n"
            + "   RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n"
            + '      OutlineColour : Colour0 = 1 : InVar_ "A"\n'
            + "      FillColour : Colour0 = 2\n"
        )
    )

    assert formatted.index("OutlineColour") < formatted.index("FillColour")
    assert 'OutlineColour : Colour0 = 1 : InVar_ "A" FillColour : Colour0 = 2' in formatted


def test_a_multi_line_comment_keeps_its_own_indentation() -> None:
    picture = parse_source_text(
        _round_trip_source(
            _ROUND_TRIP_MODULE_DEF + "MODULECODE\n   EQUATIONBLOCK :\n      (* first line\n      second line *)\n"
        ),
        log_failures=False,
    )
    assert picture.modulecode is not None
    assert picture.modulecode.equationblocks is not None
    comment = picture.modulecode.equationblocks[0].code[0]
    assert isinstance(comment, CodeComment)

    formatted = _formatted(format_source(picture))

    assert comment.text in formatted


def test_a_step_with_code_and_a_fork_round_trips() -> None:
    """``seqstep: SEQSTEP NAME? code_blocks seqfork?`` orders the fork last."""
    formatted = _formatted(
        _round_trip_source(
            "LOCALVARIABLES\n"
            "   Flag: boolean := False;\n"
            "ModuleDef\n"
            "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "MODULECODE\n"
            "   SEQUENCE Demo COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
            "      SEQINITSTEP Start\n"
            "         SEQFORK TrStart\n"
            "      SEQSTEP Work\n"
            "         ACTIVECODE\n"
            "            Flag = True;\n"
            "         SEQFORK TrEnd\n"
            "      SEQTRANSITION TrStart WAIT_FOR Flag\n"
            "      SEQTRANSITION TrEnd WAIT_FOR True\n"
            "   ENDSEQUENCE\n"
        )
    )

    step = formatted.index("SEQSTEP Work")
    assert formatted.index("ACTIVECODE", step) < formatted.index("SEQFORK TrEnd", step)
    init = formatted.index("SEQINITSTEP Start")
    assert formatted.index("SEQFORK TrStart", init) > init


def test_a_header_line_with_a_doubled_quote_is_escaped_again() -> None:
    source = (
        '"Syntax version 2.23"\n'
        '"Original file date: ---"\n'
        '"Program date: ---, name: ""hi"""\n'
        "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
        + _ROUND_TRIP_MODULE_DEF
        + "ENDDEF (*BasePicture*);\n"
    )

    formatted = _formatted(source)

    assert '"Program date: ---, name: ""hi"""' in formatted
