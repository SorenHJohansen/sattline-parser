# pyright: reportPrivateUsage=false
"""Unit tests for the structural companion record readers."""

from __future__ import annotations

import pytest

from sattline_parser.project.graphics_records import (
    DEFAULT_SYNTAX_VERSION,
    GraphicsRecordError,
    GraphicsSyntaxVersion,
    _BaselineKind,
    _open_companion,
    _read_binding,
    _read_picture_display_default,
    _Scanner,
    parse_syntax_version,
    read_companion_records,
)

_HEADER = '" Syntax version 2.23, date: 2026-10-27-12:00:00.000 N "'
_UNTERMINATED = "Unterminated graphics record; expected trailing '0' line"


def _companion(*lines: str) -> str:
    """Build companion text the way the native writer does: CRLF line endings."""
    return "".join(f"{line}\r\n" for line in lines)


def _with_header(*lines: str) -> str:
    return _companion(_HEADER, "", *lines)


def _structure(text: str) -> list[tuple[int, int | None, tuple[tuple[int, str, str], ...]]]:
    companion = read_companion_records(text)
    assert companion.error is None
    return [
        (record.family_code, record.subtype, tuple((e.index, e.kind, e.text) for e in record.entries))
        for record in companion.records
    ]


# --- scanner primitives ---------------------------------------------------------


def test_scanner_reads_numbers_and_words() -> None:
    scanner = _Scanner(_companion("  -12 7 2.5E+01 -0.5 token tail"))

    assert scanner.read_int() == -12
    assert scanner.read_short() == 7
    assert scanner.read_float() == 25.0
    assert scanner.read_double() == -0.5
    assert scanner.read_word() == "token"
    assert scanner.read_word() == "tail"
    assert scanner.eof is False
    assert scanner.line == 1


def test_scanner_word2_collapses_invalid() -> None:
    scanner = _Scanner("Invalid invalid other")

    assert scanner.read_word2() == ""
    assert scanner.read_word2() == ""
    assert scanner.read_word2() == "other"


def test_scanner_reads_lines_and_strips_carriage_return() -> None:
    scanner = _Scanner(_companion("first line", "", "third"))

    assert scanner.read_line() == "first line"
    assert scanner.read_line() == ""
    assert scanner.line == 3
    assert scanner.read_line() == "third"
    assert scanner.eof


def test_scanner_read_line_from_mid_line_and_without_trailing_newline() -> None:
    scanner = _Scanner(" 7 rest of line")
    scanner.read_int()

    assert scanner.read_line() == " rest of line"
    assert scanner.eof
    # An unterminated final line is still a line.
    scanner = _Scanner("tail")
    assert scanner.read_line() == "tail"


def test_scanner_end_line_and_getc() -> None:
    scanner = _Scanner(_companion("junk here", "t", "rest"))

    scanner.end_line()
    assert scanner.line == 2
    assert scanner.getc() == "t"
    scanner.end_line()
    assert scanner.read_word() == "rest"


def test_scanner_end_line_at_eof_is_a_no_op() -> None:
    scanner = _Scanner("")
    scanner.end_line()
    assert scanner.eof


def test_scanner_counted_payload() -> None:
    scanner = _Scanner(" 2 x\nz")

    assert scanner.read_counted() == "x "
    assert scanner.line == 2
    assert scanner.read_counted_bytes(-3) == ""
    assert scanner.read_counted_bytes(5) == "z"


def test_scanner_counted_length_zero_consumes_the_separator() -> None:
    scanner = _Scanner(" 0  tail")
    assert scanner.read_counted() == ""
    assert scanner.read_word() == "tail"


def test_scanner_column_and_value_position_tracking() -> None:
    scanner = _Scanner(_companion(" word", " 42"))

    scanner.skip_whitespace()
    assert (scanner.line, scanner.column) == (1, 2)
    assert scanner.read_word() == "word"
    assert scanner.read_int() == 42
    assert (scanner.value_line, scanner.value_column) == (2, 2)


def test_scanner_mark_skips_whitespace() -> None:
    scanner = _Scanner(_companion("", "", "  9"))
    scanner.mark()
    assert scanner.read_int() == 9


def test_scanner_reports_unterminated_at_eof() -> None:
    for reader in (
        _Scanner("").getc,
        _Scanner("").read_line,
        _Scanner("").read_word,
        _Scanner("  ").read_int,
        _Scanner("  ").read_float,
    ):
        with pytest.raises(GraphicsRecordError) as excinfo:
            _ = reader()
        assert excinfo.value.unterminated is True
        assert excinfo.value.message == _UNTERMINATED


def test_scanner_reports_unexpected_token() -> None:
    with pytest.raises(GraphicsRecordError) as excinfo:
        _ = _Scanner(_companion("word")).read_int()
    assert excinfo.value.message == "Malformed graphics record: expected an integer"
    assert excinfo.value.line == 1
    assert excinfo.value.severity == "error"

    with pytest.raises(GraphicsRecordError) as excinfo:
        _ = _Scanner(_companion("word")).read_float()
    assert excinfo.value.message == "Malformed graphics record: expected a floating-point number"


# --- syntax version -------------------------------------------------------------


def test_parse_syntax_version_from_header() -> None:
    assert parse_syntax_version(_HEADER) == GraphicsSyntaxVersion(major=2, minor=23)
    assert parse_syntax_version('" Syntax version 0.96, date: 1997"') == GraphicsSyntaxVersion(major=0, minor=96)
    assert parse_syntax_version("no header here") == DEFAULT_SYNTAX_VERSION


def test_syntax_version_capabilities() -> None:
    modern = GraphicsSyntaxVersion(major=2, minor=23)
    assert modern.reads_picture_shape_byte is True
    assert modern.uses_legacy_bindings is False
    assert modern.uses_legacy_picture_display is False

    no_shape = GraphicsSyntaxVersion(major=2, minor=18)
    assert no_shape.reads_picture_shape_byte is False
    assert no_shape.uses_legacy_bindings is False

    legacy = GraphicsSyntaxVersion(major=0, minor=96)
    assert legacy.uses_legacy_bindings is True
    assert legacy.uses_legacy_picture_display is True
    assert legacy.reads_picture_shape_byte is False

    transitional = GraphicsSyntaxVersion(major=0, minor=100)
    assert transitional.uses_legacy_bindings is True
    assert transitional.uses_legacy_picture_display is False


# --- container ------------------------------------------------------------------


def test_read_companion_records_empty_and_header_only() -> None:
    for text in ("", _HEADER, _companion(_HEADER), _companion(_HEADER, "", "  ")):
        companion = read_companion_records(text)
        assert companion.records == ()
        assert companion.error is None


def test_read_companion_records_without_header_uses_default_version() -> None:
    companion = read_companion_records(_companion(" 4", " 0 0 1 1", " 1 1 1", " 0"))

    assert companion.version == DEFAULT_SYNTAX_VERSION
    assert [record.family_code for record in companion.records] == [4]


# --- family 4 -------------------------------------------------------------------


def test_family_4_record() -> None:
    companion = read_companion_records(_with_header(" 4", " 0.0 0.0 1.0 1.0", " 1 1 1 X.Y", " 0"))

    [record] = companion.records
    assert (record.family_code, record.subtype, record.start_line, record.end_line) == (4, None, 3, 6)
    assert record.entries == ()


def test_family_4_without_optional_word() -> None:
    companion = read_companion_records(_with_header(" 4", " 0.0 0.0 1.0 1.0", " 1 1 1", " 0"))

    [record] = companion.records
    assert record.end_line == 6


# --- family 1 -------------------------------------------------------------------


def test_family_1_record_with_transcribed_discriminators() -> None:
    text = _with_header(
        " 1",
        " None  True   0.0 0.0",
        "  1.0 1.0",
        " -1 1 0 Var 0 8 ResetCnt",
        " 4 inline payload",
        " 5 1.5 2",
        " 6 2.5 3",
        " 7 another inline payload",
        " 0",
    )

    [record] = read_companion_records(text).records
    assert (record.family_code, record.start_line, record.end_line) == (1, 3, 11)


def test_family_1_unrecovered_payload_stops_with_warning() -> None:
    companion = read_companion_records(
        _with_header(" 1", " None  True  0.0 0.0", " 0.0 0.0", " -1", " 1 payload", " 0")
    )

    assert companion.records == ()
    assert companion.error is not None
    assert companion.error.severity == "warning"
    assert (
        companion.error.message
        == "Graphics record content is not recovered for family 1 discriminator 1; record scan stopped"
    )


# --- family 2 -------------------------------------------------------------------


def test_family_2_record_with_transcribed_discriminators() -> None:
    text = _with_header(
        " 2",
        " None  True   0.0 0.0",
        "  1.0 1.0",
        " 6",
        " 3",
        " 2 Var 1.5 3 abc 2.5",
        " 3 0.1 0.2 1 2 3",
        " 4 9 0.5 4 5 6",
        " 0",
    )

    [record] = read_companion_records(text).records
    assert (record.family_code, record.start_line, record.end_line) == (2, 3, 11)


def test_family_2_unrecovered_payload_stops_with_warning() -> None:
    companion = read_companion_records(_with_header(" 2", " None  True  0.0 0.0", " 0.0 0.0", " 6", " 3", " 1 x", " 0"))

    assert companion.error is not None
    assert companion.error.severity == "warning"
    assert companion.error.message.startswith("Graphics record content is not recovered for family 2 discriminator 1")


# --- family 5, subtype 1 --------------------------------------------------------


def test_family_5_subtype_1_text_table() -> None:
    text = _with_header(
        " 5",
        " Lit  True  4 True  0.00000E+000 0.00000E+000",
        "  1.00000E+000 1.00000E+000",
        " -3",
        " 1",
        "WeekDayPres",
        "",
        "12",
        "2",
        " Var 0 5 DayNo ",
        " None -3 ",
        "7",
        "1",
        "Mandag",
        "2",
        "Tirsdag",
        "3",
        "Onsdag",
        "4",
        "Torsdag",
        "5",
        "Fredag",
        "6",
        "Lordag",
        "7",
        "Sondag",
        "           0",
    )

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert (record.family_code, record.subtype) == (5, 1)
    assert record.entries == ()
    assert record.start_line == 3
    assert record.end_line == 29


# --- family 5, subtype 2 --------------------------------------------------------


def test_family_5_subtype_2_literal_entry_and_binding_default() -> None:
    text = _with_header(
        " 5",
        " Lit  True  4 True  0.00000E+00 7.14286E-02",
        "  1.00000E+00 1.42857E-01",
        " 2",
        " 2",
        " Var 0 18 Paths.OprPathIndex  None 2     1",
        "0 0 +L2+UnitControl+L1+L2+UnitPanels+L1+L2+SelectOpr ",
        " 1 Var  Invalid  19 Paths.OperationPath ",
        " Lit  True  4 True ",
        "t",
        "           0",
    )

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert (record.family_code, record.subtype) == (5, 2)
    assert [(entry.index, entry.kind, entry.text, entry.line) for entry in record.entries] == [
        (0, "literal", "+L2+UnitControl+L1+L2+UnitPanels+L1+L2+SelectOpr", 9)
    ]
    assert record.entries[0].column == 5
    assert record.end_line == 13


def test_family_5_subtype_2_variable_entries_and_inline_default() -> None:
    text = _with_header(
        " 5",
        " None  True  -2.40000E-01 1.08000E+00",
        "  1.38000E+00 1.28000E+00",
        " 0",
        " 2",
        " Var 0 12 OprPathIndex  Lit 0 2 -1     2",
        "1 1 Var  Invalid  6 PathOK",
        "2 1 Var  Invalid  9 PathNotOK",
        " 0 ",
        " None  True  ",
        "t",
        "           0",
    )

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert [(entry.index, entry.kind, entry.text, entry.column) for entry in record.entries] == [
        (1, "variable_invalid", "PathOK", 21),
        (2, "variable_invalid", "PathNotOK", 21),
    ]


def test_family_5_subtype_2_row_kinds() -> None:
    text = _with_header(
        " 5",
        " None  True  0 0",
        " 0 0",
        " 0",
        " 2",
        " None 0  None -1     4",
        "1 1 Var True 4 PVar",
        "2 1 Var Yes 4 PVar",
        "3 1 Lit Invalid 4 text",
        "4 1 Expr Invalid 4 text",
        " 0 ",
        " None  True  ",
        "t",
        "           0",
    )

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert [(entry.index, entry.kind, entry.text) for entry in record.entries] == [
        (1, "variable", "PVar"),
        (2, "other", "PVar"),
        (3, "other", "text"),
        (4, "other", "text"),
    ]


def test_family_5_subtype_2_literal_entry_with_empty_text() -> None:
    """`index SP 0` with nothing after it: `getc` consumes the CR, `LINE` the LF."""
    text = _with_header(
        " 5",
        " None  True  0 0",
        " 0 0",
        " 0",
        " 2",
        " None 0  None -1     1",
        "1 0 ",
        " 0 default",
        " None  True  ",
        "t",
        "           0",
    )

    [record] = read_companion_records(text).records
    assert [(entry.index, entry.kind, entry.text) for entry in record.entries] == [(1, "literal", "")]


def test_picture_display_resyncs_past_lines_that_cannot_open_a_record() -> None:
    companion = read_companion_records(_with_header("GRAPHICS", "", " 4", " 0 0 1 1", " 1 1 1", " 0"))

    assert companion.error is None
    assert [record.family_code for record in companion.records] == [4]


def test_literal_entry_without_trailing_separator_reads_an_empty_payload() -> None:
    text = _with_header(
        " 5",
        " None  True  0 0",
        " 0 0",
        " 0",
        " 2",
        " None 0  None -1     1",
        "1 0",
        " 0 default",
        " None  True  ",
        "t",
        "           0",
    )

    [record] = read_companion_records(text).records
    assert [(entry.index, entry.kind, entry.text) for entry in record.entries] == [(1, "literal", "")]


def test_family_5_subtype_2_without_shape_byte_for_218() -> None:
    text = _with_header(
        " 5",
        " None  True  0 0",
        " 0 0",
        " 0",
        " 2",
        " None 0  None -1     0",
        " 0 path",
        " None  True  ",
        "           0",
    ).replace("2.23", "2.18")

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert record.end_line == 11


def test_family_5_unsupported_subtype_reports_error() -> None:
    companion = read_companion_records(_with_header(" 5", " None  True  0 0", " 0 0", " 0", " 7"))

    assert companion.error is not None
    assert companion.error.severity == "error"
    assert companion.error.message == "Unsupported graphics record subtype 7"


def test_family_5_negative_subtype_is_clamped() -> None:
    companion = read_companion_records(_with_header(" 5", " None  True  0 0", " 0 0", " 0", " -3"))

    assert companion.error is not None
    assert companion.error.message == "Unsupported graphics record subtype 0"


# --- legacy layouts -------------------------------------------------------------


def test_legacy_picture_display_marker_zero() -> None:
    text = _with_header(
        " 5",
        " 0 Foo 5  0.0 0.0",
        " 0.0 0.0",
        " 0",
        " 2",
        "Title",
        "Default text",
        "12",
        "2",
        " 0 Presentation A",
        " 0 Default 5",
        "1",
        "1",
        "One",
        " 0",
    ).replace("2.23", "0.96")

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert (record.family_code, record.subtype) == (5, 2)
    assert record.end_line == 17


def test_legacy_picture_display_marker_55_then_trailing() -> None:
    text = _with_header(
        " 5",
        " 0 Foo 5  0.0 0.0",
        " 0.0 0.0",
        " 0",
        " 2",
        "Title",
        "Default text",
        "12",
        "2",
        " 0 Presentation A",
        " 0 Default 5",
        "0",
        "55",
        " 0 Bar 7",
        " 0",
    ).replace("2.23", "0.96")

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert record.end_line == 17


def test_legacy_picture_display_unknown_marker_stops_with_warning() -> None:
    text = _with_header(
        " 5",
        " 0 Foo 5  0.0 0.0",
        " 0.0 0.0",
        " 0",
        " 2",
        "Title",
        "Default text",
        "12",
        "2",
        " 0 Presentation A",
        " 0 Default 5",
        "0",
        "9",
    ).replace("2.23", "0.96")

    companion = read_companion_records(text)

    assert companion.error is not None
    assert companion.error.severity == "warning"
    assert (
        companion.error.message
        == "Graphics record content is not recovered for family 5 legacy picture-display marker 9; record scan stopped"
    )


def test_legacy_binding_layout_with_counted_reference() -> None:
    """`major == 0` bindings have no qualifier: a length, a reference, a baseline."""
    text = _companion(
        _HEADER.replace("2.23", "0.96"),
        " 3 abc True",
    )
    scanner, _version = _open_companion(text)

    binding = _read_binding(scanner, _BaselineKind.B4, GraphicsSyntaxVersion(major=0, minor=96))

    assert (binding.qualifier, binding.text, binding.baseline) == ("", "abc", "True")
    assert (binding.line, binding.column) == (2, 4)


def test_legacy_binding_layout_with_word_reference_and_integer_baseline() -> None:
    text = _companion(_HEADER.replace("2.23", "0.96"), " 0 ResetName 7")
    scanner, _version = _open_companion(text)

    binding = _read_binding(scanner, _BaselineKind.B2, GraphicsSyntaxVersion(major=0, minor=96))

    assert (binding.qualifier, binding.text, binding.baseline) == ("", "ResetName", 7)


def test_modern_binding_not_qualifier_reads_no_payload() -> None:
    scanner, version = _open_companion(_companion(" None  True  4 tail"))

    binding = _read_binding(scanner, _BaselineKind.B1, version)

    assert (binding.qualifier, binding.baseline, binding.text) == ("None", "True", "")


def test_modern_binding_var_not_baseline_reads_a_second_reference() -> None:
    scanner, version = _open_companion(_companion(" Var Not 3 abc 4 defg"))

    binding = _read_binding(scanner, _BaselineKind.B1, version)

    assert (binding.qualifier, binding.baseline, binding.text) == ("Var", "Not", "abc")


def test_picture_display_default_reads_binding_when_discriminator_is_set() -> None:
    scanner, version = _open_companion(_companion(" 1 Var Invalid 3 abc rest", "next"))

    _read_picture_display_default(scanner, version)

    assert scanner.read_word() == "next"


# --- record boundaries ----------------------------------------------------------


def test_adjacent_records_without_blank_lines() -> None:
    text = _with_header(
        " 4",
        " 0 0 1 1",
        " 1 1 1",
        " 0",
        " 4",
        " 0 0 1 1",
        " 1 1 1",
        " 0",
    )

    assert _structure(text) == [(4, None, ()), (4, None, ())]


def test_adjacent_picture_display_records_without_blank_lines() -> None:
    record = [
        " 5",
        " None  True   0.00000E+000 0.00000E+000",
        "  1.00000E+000 1.00000E+000",
        " 0",
        " 2",
        " None 0  None -1     1",
        "1 0 ++First",
        " 0 default",
        " None  True  ",
        "t",
        "           0",
    ]

    companion = read_companion_records(_with_header(*record, *record))

    assert companion.error is None
    assert [(r.subtype, [entry.text for entry in r.entries]) for r in companion.records] == [
        (2, ["++First"]),
        (2, ["++First"]),
    ]


def test_record_structure_is_independent_of_blank_lines() -> None:
    records = [
        " 4",
        " 0 0 1 1",
        " 1 1 1 X.Y",
        " 0",
        " 5",
        " None  True   0.00000E+000 0.00000E+000",
        "  1.00000E+000 1.00000E+000",
        " 0",
        " 2",
        " Var 0 13 WarningStatus  Lit -3 2 -1     2",
        "1 0 ++Oldmarked",
        "2 0 ++Forced",
        " 0 ",
        " None  True  ",
        "t",
        "           0",
    ]
    spaced = _with_header(*records)
    dense = _with_header("", *records)

    assert _structure(dense) == _structure(spaced)


def test_internal_zero_value_fields_do_not_end_a_record() -> None:
    text = _with_header(
        " 5",
        " None  True   0.00000E+000 0.00000E+000",
        "  0.00000E+000 0.00000E+000",
        " 0",
        " 2",
        " None 0  Lit 0 2 -1     1",
        "0 0 /pic/logo.bmp",
        " 0 ",
        " None  True  ",
        "t",
        "           0",
    )

    companion = read_companion_records(text)

    assert companion.error is None
    [record] = companion.records
    assert record.subtype == 2
    assert [(entry.index, entry.text) for entry in record.entries] == [(0, "/pic/logo.bmp")]


# --- failures -------------------------------------------------------------------


def test_unsupported_family_reports_error() -> None:
    companion = read_companion_records(_with_header(" 9", " 0"))

    assert companion.error is not None
    assert companion.error.message == "Unsupported graphics record family 9"
    assert companion.error.line == 3


def test_unterminated_record_reports_start_line() -> None:
    companion = read_companion_records(_with_header(" 4", " 0 0 1 1", " 1 1 1", ""))

    assert companion.error is not None
    assert companion.error.message == _UNTERMINATED
    assert companion.error.line == 3


def test_previous_records_survive_a_later_failure() -> None:
    text = _with_header(" 4", " 0 0 1 1", " 1 1 1", " 0", " 4", " 0 0 1 1", " 1 1 1")

    companion = read_companion_records(text)

    assert [record.start_line for record in companion.records] == [3]
    assert companion.error is not None
