# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from sattline_parser.preprocessing.comments import CommentStrippedText

from ._parser_core_test_support import *


def test_strip_sl_comments_with_mapping_remaps_inline_comment_columns():
    source = """\
\"SyntaxVersion\"
\"OriginalFileDate\"
\"ProgramDate\"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        DemoValue = 1; (* inline comment *) ???
ENDDEF (*BasePicture*);
"""

    stripped = strip_sl_comments_with_mapping(source)
    cleaned_line = stripped.text.splitlines()[8]
    cleaned_column = cleaned_line.index("?") + 1

    assert stripped.map_line_column(9, cleaned_column) == (9, source.splitlines()[8].index("?") + 1)


def test_strip_sl_comments_with_mapping_handles_crlf_nested_comments_and_string_edges():
    source = '"unterminated\rA\r\n"He said ""Hi""" "A\\B" (* outer\r\n(* inner *)\ncomment *)\r\n   ;\rNext = 1;\n'

    stripped = strip_sl_comments_with_mapping(source)

    assert strip_sl_comments(source) == stripped.text
    assert '"unterminated\rA\r\n' in stripped.text
    assert '"He said ""Hi""" "A\\B" ' in stripped.text
    assert "(*" not in stripped.text
    assert stripped.text.endswith("\r\n   \rNext = 1;\n")


def test_comment_stripped_text_map_line_column_covers_bounds_and_fallbacks():
    source = "Alpha\r\nBeta (* comment *) Gamma"
    stripped = strip_sl_comments_with_mapping(source)
    cleaned_line = stripped.text.splitlines()[1]
    gamma_column = cleaned_line.index("Gamma") + 1

    assert stripped.map_line_column(None, 2) == (None, 2)
    assert stripped.map_line_column(0, 0) == (0, 0)
    assert stripped.map_line_column(99, 1) == (99, 1)
    assert stripped.map_line_column(2, gamma_column) == (2, source.splitlines()[1].index("Gamma") + 1)
    assert stripped.map_line_column(2, 999) == (2, len(source.splitlines()[1]) + 1)

    fallback = CommentStrippedText(
        text="A",
        cleaned_offsets_to_original=(0, 1),
        original_line_starts=(),
        cleaned_line_starts=(0,),
    )
    assert fallback.map_line_column(1, 1) == (1, 1)


def test_strip_sl_comments_preserves_trailing_backslash_at_end_of_string():
    assert strip_sl_comments('"abc\\') == '"abc\\'


def test_preprocess_sl_text_injects_modulecode_before_equationblock_when_missing():
    decoded, mapping = preprocess_sl_text("MODULEDEFINITION Demo EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :")

    assert "MODULEDEFINITION Demo ModuleCode EQUATIONBLOCK Main" in decoded
    assert mapping["#84"] == "ModuleCode"
