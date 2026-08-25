# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403
from sattline_parser.preprocessing import MAX_IDE_LINE_LENGTH, render_ide_text

from ._parser_core_test_support import *


def test_render_ide_text_normalizes_line_endings_to_crlf():
    assert render_ide_text("a\nb\rc\r\nd") == "a\r\nb\r\nc\r\nd"


def test_render_ide_text_wraps_long_lines_at_last_space_within_limit():
    raw = "TextObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 ) " + "x" * 120 + " tail"
    out = render_ide_text(raw)
    lines = out.split("\r\n")

    assert all(len(line) <= MAX_IDE_LINE_LENGTH for line in lines)
    assert out == render_ide_text(out)


def test_render_ide_text_never_splits_quoted_strings():
    # Spaces inside the string must not become break points; the break has to
    # wait for the space after the closing quote.
    raw = '"short string here"' + " " + "w" * 140
    first, second = render_ide_text(raw).split("\r\n")

    assert first == '"short string here"'
    assert second == "w" * 140


def test_render_ide_text_leaves_unsplittable_lines_intact():
    unbreakable = "z" * (MAX_IDE_LINE_LENGTH + 40)

    assert render_ide_text(unbreakable) == unbreakable


def test_render_ide_text_reproduces_batchlib_roundtrip_split():
    # Real overlong line from the decoded BatchLib corpus; this exact split
    # was accepted by the IDE.
    raw = (
        "Value_Changed = True : OutVar_ \"CopyPasteChanged\" Variable = 0 : OutVar_ \"EditCommand\" "
        "Abs_ TextObject = 0 : InVar_ 1   ComBut_ ( 5.96046E-08 , 0.5 )  ( 0.5 , 1.0 )  Int_Value Layer_ = "
    )
    first, second = render_ide_text(raw).split("\r\n")

    assert len(first) <= MAX_IDE_LINE_LENGTH
    assert first.endswith("ComBut_ (")
    assert second.startswith("5.96046E-08")
