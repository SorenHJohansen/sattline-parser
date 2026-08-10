# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_unexpected_input_summary_formats_eof_token_and_character_variants():
    class FakeUnexpectedEOF(UnexpectedEOF):
        def __init__(self) -> None:
            self._expected_reads = 0

        def __getattribute__(self, name: str):
            if name == "expected":
                reads = object.__getattribute__(self, "_expected_reads")
                object.__setattr__(self, "_expected_reads", reads + 1)
                if reads == 0:
                    return []
                return {"ENDDEF", "LOCALVARIABLES"}
            return object.__getattribute__(self, name)

        def __str__(self) -> LiteralString:
            return "Unexpected end of input"

    class FakeUnexpectedToken(UnexpectedToken):
        def __init__(self) -> None:
            self._expected_reads = 0
            object.__setattr__(self, "token", "BADTOKEN")

        def __getattribute__(self, name: str):
            if name == "expected":
                reads = object.__getattribute__(self, "_expected_reads")
                object.__setattr__(self, "_expected_reads", reads + 1)
                if reads == 0:
                    return []
                return {"ENDDEF", "LOCALVARIABLES"}
            return object.__getattribute__(self, name)

        def __str__(self) -> str:
            return "Unexpected token BADTOKEN"

    class FakeUnexpectedCharacters(UnexpectedCharacters):
        def __init__(self) -> None:
            pass

        def __str__(self) -> str:
            return "Invalid character."

    eof_summary = parser_api._unexpected_input_summary(FakeUnexpectedEOF())
    token_summary = parser_api._unexpected_input_summary(FakeUnexpectedToken())
    char_summary = parser_api._unexpected_input_summary(FakeUnexpectedCharacters())

    assert eof_summary == "Unexpected end of input. Expected one of: ENDDEF, LOCALVARIABLES"
    assert token_summary == "Unexpected token 'BADTOKEN'. Expected one of: ENDDEF, LOCALVARIABLES"
    assert char_summary == "Invalid character"


def test_unexpected_input_summary_appends_expected_items_when_present_on_first_read():
    class FakeUnexpectedInput(UnexpectedEOF):
        def __init__(self) -> None:
            pass

        expected = cast(Any, {"BETA", "ALPHA"})

        def __str__(self) -> LiteralString:
            return "Unexpected parse issue"

    summary = parser_api._unexpected_input_summary(FakeUnexpectedInput())

    assert summary == "Unexpected parse issue. Expected one of: ALPHA, BETA"


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
        message="Unexpected end of input. Expected one of: ENDIF\nline context",
        line=4,
        column=9,
    )


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


def test_describe_parse_error_remaps_locations_from_inline_comment_stripped_source():
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
    stripped = parser_api.strip_sl_comments(source)
    cleaned_line = stripped.splitlines()[8]
    cleaned_column = cleaned_line.index("?") + 1
    original_column = source.splitlines()[8].index("?") + 1

    class FakeUnexpectedInput(UnexpectedEOF):
        def __init__(self) -> None:
            pass

        line = 9
        column = cleaned_column
        expected = cast(Any, {"NAME"})

        def __str__(self) -> LiteralString:
            return "Unexpected end of input"

        def get_context(self, text: str, span: int = 40) -> str:
            raise AssertionError("mapped parse errors should render context from the original source")

    details = parser_api.describe_parse_error(FakeUnexpectedInput(), source)

    assert details.line == 9
    assert details.column == original_column
    assert "DemoValue = 1; (* inline comment *) ???" in details.message
    assert "^" in details.message
