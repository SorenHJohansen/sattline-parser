# pyright: reportPrivateUsage=false
from typing import Any, LiteralString, cast

import pytest
from lark import Token
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

from sattline_parser import errors as parser_errors
from sattline_parser import parse_source_text as parser_core_parse_source_text
from sattline_parser.errors import ParseErrorDetails, describe_parse_error


def _parse_failure(expected: set[str], *, token: object, line: int = 4) -> Any:
    """A minimal UnexpectedToken stand-in for message tests."""

    class _Failure(UnexpectedToken):
        def __init__(self) -> None:
            object.__setattr__(self, "token", token)
            object.__setattr__(self, "line", line)
            object.__setattr__(self, "column", 9)
            object.__setattr__(self, "expected", expected)

        def __str__(self) -> str:
            return "raw lark text"

    return _Failure()


def _character_failure(char: str) -> Any:
    class _Failure(UnexpectedCharacters):
        def __init__(self) -> None:
            object.__setattr__(self, "char", char)
            object.__setattr__(self, "line", 1)
            object.__setattr__(self, "column", 1)
            object.__setattr__(self, "expected", set())

        def __str__(self) -> str:
            return "raw lark text"

    return _Failure()


def test_parse_failure_sentence_names_what_was_found_and_expected():
    eof = _parse_failure({"ENDDEF_KW", "LOCALVARIABLES"}, token=Token("$END", ""))
    token = _parse_failure({"ENDDEF_KW", "LOCALVARIABLES"}, token=Token("NAME", "BADTOKEN"))
    character = _character_failure("?")

    assert parser_errors._unexpected_description(eof)[0] == (
        "unexpected end of file; expected 'ENDDEF' or 'LOCALVARIABLES'"
    )
    assert parser_errors._unexpected_description(token)[0] == (
        "unexpected 'BADTOKEN'; expected 'ENDDEF' or 'LOCALVARIABLES'"
    )
    assert parser_errors._unexpected_description(character)[0] == "unexpected character '?'"


def test_parse_failure_sentence_renders_punctuation_and_phrases():
    missing_semicolon = _parse_failure({"SEMICOLON", "ENDDEF_KW"}, token=Token("$END", ""))
    header = _parse_failure({"STRING", "NAME"}, token=Token("NAME", "x"), line=1)

    assert parser_errors._unexpected_description(missing_semicolon)[0] == (
        "unexpected end of file; expected ';' or 'ENDDEF'"
    )
    assert parser_errors._unexpected_description(header)[0] == "unexpected 'x'; expected a name or a string"


def test_parse_failure_sentence_caps_the_expectation_list():
    expected = {"ENDDEF_KW", "LOCALVARIABLES", "MODULEDEF", "SUBMODULES", "TYPEDEFINITIONS", "MODULEPARAMETERS"}
    sentence = parser_errors._unexpected_description(_parse_failure(expected, token=Token("$END", "")))[0]

    assert sentence.count("'") == 2 * 5


def test_parse_error_hints_are_actionable():
    missing_semicolon = _parse_failure({"SEMICOLON"}, token=Token("$END", ""))
    header = _parse_failure({"STRING"}, token=Token("NAME", "BasePicture"), line=1)
    typo = _parse_failure({"ENDDEF_KW"}, token=Token("NAME", "ENDDE"))

    _, semicolon_hint, _, _ = parser_errors._unexpected_description(missing_semicolon)
    _, header_hint, _, _ = parser_errors._unexpected_description(header)
    _, typo_hint, _, _ = parser_errors._unexpected_description(typo)

    assert semicolon_hint == "the unit ends before a required ';'; the last construct is incomplete"
    assert header_hint is not None and header_hint.startswith("a unit starts with three quoted header lines")
    assert typo_hint == "did you mean 'ENDDEF'?"


def test_describe_parse_error_reports_structured_parts():
    failure = _parse_failure({"SEMICOLON"}, token=Token("$END", ""), line=1)
    details = describe_parse_error(failure, "ENDDEF (*BasePicture*)")

    assert details.found is None
    assert details.expected == ("';'",)
    assert details.hint == "the unit ends before a required ';'; the last construct is incomplete"
    assert details.source_line == "ENDDEF (*BasePicture*)"
    assert "Token(" not in details.message
    assert details.message.startswith("unexpected end of file; expected ';'")
    assert details.message.splitlines()[1].startswith("help: ")


def test_describe_parse_error_includes_context_for_unexpected_input():
    class FakeUnexpectedInput(UnexpectedEOF):
        def __init__(self) -> None:
            pass

        line = 4
        column = 9
        expected = cast(Any, {"ENDIF"})

        def __str__(self) -> LiteralString:
            return "Unexpected end of input"

        def get_context(self, text: str, span: int = 40) -> str:
            assert text == "IF X THEN"
            assert span == 40
            return "line context\n"

    details = describe_parse_error(FakeUnexpectedInput(), "IF X THEN")

    assert details == ParseErrorDetails(
        message=(
            "unexpected end of file; expected 'ENDIF'\n"
            "help: the unit ends unexpectedly; the last construct is incomplete\n"
            "line context"
        ),
        line=4,
        column=9,
        sentence="unexpected end of file; expected 'ENDIF'",
        found=None,
        expected=("'ENDIF'",),
        hint="the unit ends unexpectedly; the last construct is incomplete",
        source_line=None,
    )


def test_describe_parse_error_on_a_real_unit_names_the_missing_terminator():
    source = (
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*)\n"
    )
    with pytest.raises(UnexpectedInput) as exc_info:
        parser_core_parse_source_text(source)

    details = describe_parse_error(exc_info.value, source)

    assert details.line == 7
    assert "Token(" not in details.message
    assert "';'" in details.message
    assert details.hint is not None and "';'" in details.hint
    assert details.source_line == "ENDDEF (*BasePicture*)"
    assert "ENDDEF (*BasePicture*)" in details.message


def test_describe_parse_error_falls_back_to_plain_exception_message():
    class PlainFailureError(Exception):
        def __init__(self) -> None:
            super().__init__("plain failure")
            self.line = 7
            self.column = 11

    details = describe_parse_error(PlainFailureError(), "ignored")

    assert details.message == "plain failure"
    assert details.line == 7
    assert details.column == 11


def test_describe_parse_error_locations_map_directly_to_original_source():
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
    original_column = source.splitlines()[8].index("?") + 1
    line_start = sum(len(line) + 1 for line in source.splitlines()[:8])
    stream_pos = line_start + original_column - 1

    class FakeUnexpectedInput(UnexpectedEOF):
        def __init__(self) -> None:
            pass

        line = 9
        column = original_column
        pos_in_stream = stream_pos
        expected = cast(Any, {"NAME"})

        def __str__(self) -> LiteralString:
            return "Unexpected end of input"

    details = describe_parse_error(FakeUnexpectedInput(), source)

    assert details.line == 9
    assert details.column == original_column
    assert "DemoValue = 1; (* inline comment *) ???" in details.message
    assert "^" in details.message


def test_source_line_needs_a_usable_line_number():
    assert parser_errors._source_line("text", None) is None
    assert parser_errors._source_line("text", 0) is None
    assert parser_errors._source_line("a\nb", 2) == "b"
    assert parser_errors._source_line("a", 9) is None


def test_source_line_splits_on_every_line_terminator():
    # CRLF, LF, and a lone CR each end a line, the same rule the grammar's
    # string terminals and SourceDocument.line_col use.
    source = "a\rb\nsecond\r\nthird\n"
    assert parser_errors._source_line(source, 1) == "a"
    assert parser_errors._source_line(source, 2) == "b"
    assert parser_errors._source_line(source, 3) == "second"
    assert parser_errors._source_line(source, 4) == "third"
    # A trailing terminator leaves the boundary line empty, exactly like a
    # trailing "\n" split.
    assert parser_errors._source_line(source, 5) == ""
    # Form feed and vertical tab are content, not line separators.
    assert parser_errors._source_line("a\vb\fc", 1) == "a\vb\fc"


def test_describe_parse_error_source_line_uses_the_same_splitting():
    source = '"a"\rsecond\rthird\r'
    failure = _parse_failure({"SEMICOLON"}, token=Token("$END", ""), line=2)

    details = describe_parse_error(failure, source)

    assert details.source_line == "second"


def test_a_remapped_context_window_splits_lines_on_a_lone_cr():
    """The excerpt and the caret follow the reported line, not an LF count.

    A CR-only document is three physical lines here. Lark's ``get_context``
    ends a line at LF only, so it would return the whole document as one window
    and put the caret at the wrong place.
    """
    from sattline_parser.source_document import SourceDocument, remap_parse_error  # noqa: PLC0415

    source = "first\rsecond\rbad line\rfourth\r"
    position = source.index("line")
    failure = UnexpectedCharacters(source, position, 3, 5, allowed=cast(Any, {"NAME"}))
    remap_parse_error(failure, SourceDocument.identity(source))

    details = describe_parse_error(failure, source)

    assert details.line == 3
    assert details.column == 5
    assert details.source_line == "bad line"
    context = details.message.splitlines()[-2]
    assert context == "bad line"
    assert details.message.splitlines()[-1] == "    ^"


def test_a_mapped_context_window_splits_lines_on_a_lone_cr():
    """Mapping an offset back keeps the window on the original physical line."""
    from sattline_parser.source_document import SourceDocument  # noqa: PLC0415

    # One deleted character; the surviving text still has lone CR terminators.
    original = "a\rXb\rc"
    normalized = "a\rb\rc"
    document = SourceDocument(original, normalized, (0, 1, 3, 4, 5))
    failure = UnexpectedCharacters(normalized, 2, 2, 1, allowed=cast(Any, {"NAME"}))

    details = describe_parse_error(failure, original, source_document=document)

    assert details.line == 2
    assert details.column == 2
    assert details.source_line == "Xb"
    assert details.message.splitlines()[-2] == "Xb"
    assert details.message.splitlines()[-1] == " ^"


def test_sampled_pattern_terminals_have_friendly_display_names():
    spellings = parser_errors._terminal_spellings()
    for name in (
        "REAL_NOTAIL",
        "SIGNED_INT_NOTAIL",
        "STRING_NOTAIL",
        "BOOL_NOTAIL",
        "BOOL",
        "STATE_SUFFIX",
        "COMMENT_TEXT",
    ):
        label = parser_errors._terminal_label(name, spellings)
        assert name not in label
        assert label

    # A name with no entry is spelled out as words rather than printed raw.
    assert parser_errors._terminal_label("SOMETHING_ODD", {}) == "a something odd"
    assert parser_errors._terminal_label("ODD_NOTAIL", {}) == "an odd"
    # A ``_NOTAIL`` twin of a tabled terminal reuses the base phrase.
    assert parser_errors._terminal_label("STATE_SUFFIX_NOTAIL", {}) == parser_errors._TERMINAL_DISPLAY["STATE_SUFFIX"]


def test_a_real_failure_never_prints_a_lark_terminal_name():
    expected = {"REAL_NOTAIL", "SIGNED_INT_NOTAIL", "STRING_NOTAIL", "BOOL_NOTAIL", "BOOL"}
    sentence = parser_errors._unexpected_description(_parse_failure(expected, token=Token("$END", "")))[0]

    assert "_NOTAIL" not in sentence
    assert "a number" in sentence
    assert "an integer" in sentence
    assert "a string" in sentence
    assert "a boolean" in sentence
