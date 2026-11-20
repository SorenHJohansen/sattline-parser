from sattline_parser.api import parse_source_text
from sattline_parser.preprocessing import MAX_IDE_LINE_LENGTH, render_ide_text


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
        'Value_Changed = True : OutVar_ "CopyPasteChanged" Variable = 0 : OutVar_ "EditCommand" '
        "Abs_ TextObject = 0 : InVar_ 1   ComBut_ ( 5.96046E-08 , 0.5 )  ( 0.5 , 1.0 )  Int_Value Layer_ = "
    )
    first, second = render_ide_text(raw).split("\r\n")

    assert len(first) <= MAX_IDE_LINE_LENGTH
    assert first.endswith("ComBut_ (")
    assert second.startswith("5.96046E-08")


def test_render_ide_text_never_splits_a_quoted_identifier():
    # The only space within the limit after the assignment is inside the quoted
    # name. Breaking there would cut one token into two.
    quoted = "'" + "a" * 10 + " " + "b" * 140 + "'"
    raw = "X := " + quoted + " + 1"

    rendered = render_ide_text(raw)

    assert quoted in rendered
    assert rendered.split("\r\n") == ["X :=", quoted + " + 1"]


def test_rendered_text_with_an_overlong_quoted_identifier_still_parses():
    quoted = "'" + "a" * 10 + " " + "b" * 140 + "'"
    program = (
        '"SyntaxVersion"\n"OriginalFileDate"\n"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        f"    {quoted}: integer;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        f"        {quoted} = 1;\n"
        "ENDDEF (*BasePicture*);\n"
    )

    rendered = render_ide_text(program)

    assert quoted in rendered
    assert parse_source_text(rendered, log_failures=False).name == "BasePicture"
