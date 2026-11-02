# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from sattline_parser import errors as parser_errors

from ._parser_core_test_support import *


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


def test_unexpected_input_summary_names_what_was_found_and_expected():
    eof = _parse_failure({"ENDDEF_KW", "LOCALVARIABLES"}, token=Token("$END", ""))
    token = _parse_failure({"ENDDEF_KW", "LOCALVARIABLES"}, token=Token("NAME", "BADTOKEN"))
    character = _character_failure("?")

    assert parser_api._unexpected_input_summary(eof) == (
        "unexpected end of file; expected 'ENDDEF' or 'LOCALVARIABLES'"
    )
    assert parser_api._unexpected_input_summary(token) == (
        "unexpected 'BADTOKEN'; expected 'ENDDEF' or 'LOCALVARIABLES'"
    )
    assert parser_api._unexpected_input_summary(character) == "unexpected character '?'"


def test_unexpected_input_summary_renders_punctuation_and_phrases():
    missing_semicolon = _parse_failure({"SEMICOLON", "ENDDEF_KW"}, token=Token("$END", ""))
    header = _parse_failure({"STRING", "NAME"}, token=Token("NAME", "x"), line=1)

    assert parser_api._unexpected_input_summary(missing_semicolon) == (
        "unexpected end of file; expected ';' or 'ENDDEF'"
    )
    assert parser_api._unexpected_input_summary(header) == ("unexpected 'x'; expected a name or a string")


def test_unexpected_input_summary_caps_the_expectation_list():
    expected = {"ENDDEF_KW", "LOCALVARIABLES", "MODULEDEF", "SUBMODULES", "TYPEDEFINITIONS", "MODULEPARAMETERS"}
    summary = parser_api._unexpected_input_summary(_parse_failure(expected, token=Token("$END", "")))

    assert summary.count("'") == 2 * 5


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
    details = parser_api.describe_parse_error(failure, "ENDDEF (*BasePicture*)")

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

    details = parser_api.describe_parse_error(FakeUnexpectedInput(), "IF X THEN")

    assert details == parser_api.ParseErrorDetails(
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

    details = parser_api.describe_parse_error(exc_info.value, source)

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

    details = parser_api.describe_parse_error(PlainFailureError(), "ignored")

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

    details = parser_api.describe_parse_error(FakeUnexpectedInput(), source)

    assert details.line == 9
    assert details.column == original_column
    assert "DemoValue = 1; (* inline comment *) ???" in details.message
    assert "^" in details.message


def test_source_line_needs_a_usable_line_number():
    assert parser_errors._source_line("text", None) is None
    assert parser_errors._source_line("text", 0) is None
    assert parser_errors._source_line("a\nb", 2) == "b"
    assert parser_errors._source_line("a", 9) is None
