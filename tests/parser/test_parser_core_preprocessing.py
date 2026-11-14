# pyright: reportPrivateUsage=false
from pathlib import Path

import pytest

from sattline_parser import source_io as parser_api
from sattline_parser.preprocessing import is_compressed, preprocess_source
from sattline_parser.preprocessing.compressed import (
    _MARKER_RE,
    SCANNER_TOKENS,
    _align_replacement,
    _decode_markers,
    _decode_with_map,
    _header_compression_flag,
    _regex_sub,
    scan_opaque_regions,
)
from sattline_parser.source_document import GENERATED, Generated


def test_is_compressed_ignores_markers_inside_comments():
    src = "(* signal tags: #aa #bb #cc #dd #ee #ff #gg #hh #ii #jj #kk #ll #mm #nn *)\nMODULEDEFINITION Demo\nENDDEF\n"

    assert is_compressed(src) is False


def test_is_compressed_ignores_markers_inside_strings():
    src = 'MODULEDEFINITION Demo\nENDDEF\nSomeVar := "tags #aa #bb #cc #dd #ee #ff #gg #hh #ii #jj";\n'

    assert is_compressed(src) is False


def test_is_compressed_still_detects_structural_markers_when_strings_contain_markers():
    src = " ".join(["#01X"] * 10) + ' "tags #aa #bb #cc #dd #ee #ff #gg #hh #ii #jj"'

    assert is_compressed(src) is True


def test_is_compressed_uses_the_weak_marker_rule_without_structure_keywords():
    # Ten markers, far below the 2% character share, and no structural keyword:
    # the weak rule is what decides.
    src = " ".join(["#01"] * 10) + " " + "x" * 3000

    assert is_compressed(src) is True


def test_is_compressed_keeps_prose_with_a_structure_keyword_plain():
    # The same marker density, but the body names MODULEDEFINITION, so the weak
    # rule must not fire.
    src = " ".join(["#01"] * 10) + " MODULEDEFINITION Demo " + "x" * 3000

    assert is_compressed(src) is False


def test_plain_source_with_marker_like_strings_is_not_preprocessed():
    src = (
        "MODULEDEFINITION Demo\n"
        "IF SomeVar THEN\n"
        "    x := 1\n"
        "ENDIF\n"
        'SomeVar := "tags #aa #bb #cc #dd #ee #ff #gg #hh #ii #jj";\n'
        "ENDDEF\n"
    )

    doc = preprocess_source(src)

    assert doc.is_identity()
    assert doc.normalized_text == src
    assert "ENDIF;" not in doc.normalized_text


def test_decode_stages_compose_identically_to_decode_with_map():
    text = (
        "#71 Demo #84 #01Tail ENDIF; #8? 5; "
        "TrueVar integer ENDDEF "
        '"string with #71 and #8? inside" (* comment with #84 *)'
    )

    registry, decoded, char_map = _decode_markers(text, dict(SCANNER_TOKENS))
    restored, restored_map = registry.restore(decoded, char_map)
    full_decoded, full_map = _decode_with_map(text, dict(SCANNER_TOKENS))

    assert restored == full_decoded
    assert tuple(restored_map) == tuple(full_map)


def test_decode_markers_stage_protects_strings_from_unknown_markers():
    text = '#71 Demo ENDDEF "text #99 unknown"'

    registry, decoded, char_map = _decode_markers(text, dict(SCANNER_TOKENS))
    restored, _restored_map = registry.restore(decoded, char_map)

    assert '"text #99 unknown"' in restored


def test_scanner_tokens_expands_marker_70_to_composite_object():
    assert SCANNER_TOKENS["#70"] == "CompositeObject"


def test_scan_opaque_regions_recognizes_a_quoted_identifier():
    assert scan_opaque_regions("A := '#84';") == [("S", 5, 10)]


def test_scan_opaque_regions_ignores_an_unterminated_apostrophe():
    assert scan_opaque_regions("A := 1 + 'unterminated") == []


def test_scan_opaque_regions_treats_an_apostrophe_inside_a_name_as_name_text():
    # ``Pump'A`` is one unquoted name, so neither apostrophe opens a region and
    # the marker between two such names stays visible to the decoder.
    assert scan_opaque_regions("Pump'A #84 Pump'B") == []


def test_compressed_marker_between_apostrophe_names_is_decoded():
    src = "\"Syntax version 2.23, date: 2026-08-26-11:48:22.200 C\"\nPump'A #84 Pump'B\n"

    assert preprocess_source(src).normalized_text.endswith("Pump'A ModuleCode Pump'B\n")


def test_scan_opaque_regions_ends_a_description_at_the_line_break():
    text = 'Value: integer "open description\nMore: integer;'

    assert scan_opaque_regions(text) == [("S", 15, 32)]


def test_compressed_markers_inside_a_quoted_identifier_stay_literal():
    src = "\"Syntax version 2.23 C\"\nSomeVar := '#84';\n"

    doc = preprocess_source(src)

    assert "'#84'" in doc.normalized_text
    assert "ModuleCode" not in doc.normalized_text


def test_an_unknown_marker_inside_a_quoted_identifier_is_not_an_error():
    src = "\"Syntax version 2.23 C\"\nSomeVar := '#00';\n"

    doc = preprocess_source(src)

    assert "'#00'" in doc.normalized_text


def test_an_unterminated_description_does_not_shield_the_next_line():
    src = '"Syntax version 2.23 C"\nLOCALVARIABLES\n   Value: integer "description with no closing quote\n#71 Demo\n'

    doc = preprocess_source(src)

    assert "MODULEDEFINITION Demo" in doc.normalized_text
    assert "#71" not in doc.normalized_text


def test_a_marker_inside_an_unterminated_description_stays_literal():
    src = '"Syntax version 2.23 C"\nLOCALVARIABLES\n   Value: integer "description #84\n#71 Demo\n'

    doc = preprocess_source(src)

    assert '"description #84' in doc.normalized_text
    assert "MODULEDEFINITION Demo" in doc.normalized_text


# ---------------------------------------------------------------------------
# Generated-text provenance (first-class distinction)
# ---------------------------------------------------------------------------


def test_generated_provenance_is_a_first_class_int_like_sentinel():
    assert type(GENERATED) is Generated
    assert isinstance(GENERATED, int)
    assert GENERATED == -1
    assert GENERATED < 0
    assert repr(GENERATED) == "GENERATED"


def test_regex_sub_marker_expansion_keeps_real_suffix_aligned():
    decoded, char_map = _regex_sub("#0<Remark", list(range(9)), _MARKER_RE, lambda m: "* " + m.group(0)[3:])
    assert decoded == "* Remark"
    assert char_map == [GENERATED, GENERATED, 3, 4, 5, 6, 7, 8]


def test_align_replacement_edge_cases():
    assert _align_replacement("", "abc", [0, 1, 2]) == []
    assert _align_replacement("x", "abc", [0, 1, 2]) == [GENERATED]
    assert _align_replacement("ENDIF;", "ENDIF", [0, 1, 2, 3, 4]) == [0, 1, 2, 3, 4, GENERATED]
    assert _align_replacement("axc", "abc", [0, 1, 2]) == [0, GENERATED, 2]


# ---------------------------------------------------------------------------
# Header-flag compression detection
# ---------------------------------------------------------------------------


def test_header_compression_flag_c():
    assert _header_compression_flag('"Syntax version 2.23, date: 2026-08-26-11:48:22.200 C"\n') == "C"


def test_header_compression_flag_n():
    assert _header_compression_flag('"Syntax version 2.23, date: 2026-08-26-11:48:22.200 N"\n') == "N"


def test_header_compression_flag_missing():
    assert _header_compression_flag("No header line here\n") is None


def test_header_compression_flag_empty():
    assert _header_compression_flag("") is None


def test_is_compressed_header_c_overrides_heuristics():
    # Header says C → is_compressed must return True regardless of content
    src = '"Syntax version 2.23, date: 2026-08-26-11:48:22.200 C"\nPlain text with no markers\n'
    assert is_compressed(src) is True


def test_is_compressed_header_n_overrides_heuristics():
    # Header says N → is_compressed must return False even with many markers
    markers = " ".join(["#01X"] * 60)
    src = '"Syntax version 2.23, date: 2026-08-26-11:48:22.200 N"\n' + markers + "\n"
    assert is_compressed(src) is False


def test_is_compressed_no_header_falls_back_to_heuristics():
    # No header → heuristic applies
    assert is_compressed("MODULEDEFINITION Demo EQUATIONBLOCK Main") is False
    assert is_compressed(" ".join(["#01X"] * 10)) is True


def test_is_compressed_header_n_with_compressed_markers_in_text():
    # Regression: CompressedSequenceBasic.s has header=N but contains #6? #01 etc.
    header_n_with_markers = (
        '"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"\nBasePicture #6? #01 0.0 , 0.0 ) #8= #71 #81 1\n'
    )
    assert is_compressed(header_n_with_markers) is False


# ---------------------------------------------------------------------------
# Marker shape
# ---------------------------------------------------------------------------


def test_a_marker_is_a_hash_plus_two_characters_from_the_ordinal_run():
    assert _MARKER_RE.findall("#01 #8? #;> #0< #:=") == ["#01", "#8?", "#;>", "#0<", "#:="]
    # The format never produces a one-character code or a letter-bearing one, so
    # those are ordinary text rather than markers.
    assert _MARKER_RE.findall("#8 #aa #ZZ #ABCDEF") == []


def test_a_one_character_hash_sequence_is_not_decoded_as_a_marker():
    # `#8` followed by a space is not a marker: a marker is always `#` plus two
    # characters from the ordinal run.
    source = '"Syntax version 2.23 C"\nSomeVar := #8 ;\n'

    document = preprocess_source(source)

    assert "#8 " in document.normalized_text


# ---------------------------------------------------------------------------
# Fast paths in the decoder (behaviour must not change)
# ---------------------------------------------------------------------------


def test_align_replacement_short_circuits_when_no_character_survives():
    # The common keyword expansion shares no character with its `#NN` code.
    assert _align_replacement("ModuleCode", "#84", [10, 11, 12]) == [GENERATED] * len("ModuleCode")
    # A shared character is still aligned to its source offset.
    assert _align_replacement("ENDIF;", "ENDIF", [0, 1, 2, 3, 4]) == [0, 1, 2, 3, 4, GENERATED]


def test_a_large_compressed_source_decodes_identically_to_the_expected_text():
    from sattline_parser.preprocessing.compressed import decode_compressed  # noqa: PLC0415

    fragment = "#71 Demo #84 #01 Tail ENDIF; #8? 5; (* note #71 *) "
    repetitions = 4000
    header = '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 C"\n'
    source = header + fragment * repetitions
    expected_fragment = decode_compressed(fragment, dict(SCANNER_TOKENS))

    document = preprocess_source(source)

    assert len(source) > 100_000
    assert document.normalized_text == header + expected_fragment * repetitions
    char_map = document.char_map
    assert char_map is not None
    assert len(char_map) == len(document.normalized_text)
    # Every real mapping points at the same character in the original source;
    # every other entry is the generated sentinel.
    for index, offset in enumerate(char_map):
        if offset >= 0:
            assert source[offset] == document.normalized_text[index]


def test_a_compressed_file_that_decodes_to_itself_is_an_identity_document():
    # Header-flagged but marker-free: there is nothing to map.
    source = '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 C"\nSomeVar := 1;\n'

    document = preprocess_source(source)

    assert is_compressed(source) is True
    assert document.is_identity() is True
    assert document.char_map is None
    assert document.normalized_text == source


# ---------------------------------------------------------------------------
# File reading: one snapshot, BOM, closed comments
# ---------------------------------------------------------------------------

_BOM_PROGRAM = (
    '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-10-26-12:00:00.000, name: Bom"\n'
    "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ENDDEF (*BasePicture*);\n"
)


def test_a_utf8_bom_is_stripped_before_the_cp1252_decode(tmp_path: Path) -> None:
    source = tmp_path / "Bom.s"
    source.write_bytes(b"\xef\xbb\xbf" + _BOM_PROGRAM.encode("cp1252"))

    assert parser_api.read_text_cp1252(source) == _BOM_PROGRAM
    assert parser_api.decode_source_bytes(source.read_bytes()) == _BOM_PROGRAM
    picture = parser_api.parse_source_file(source, log_failures=False)
    assert picture.name == "BasePicture"
    assert picture.header.declaration_span is not None
    assert picture.header.declaration_span.column == 1


def test_load_source_text_reads_the_file_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "Once.s"
    source.write_bytes(_BOM_PROGRAM.encode("cp1252"))
    reads: list[Path] = []
    original = Path.read_bytes

    def _counting_read(path: Path) -> bytes:
        reads.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", _counting_read)

    assert parser_api.load_source_text(source) == _BOM_PROGRAM
    assert reads == [source]


def test_undefined_byte_inside_a_closed_nested_comment_is_tolerated(tmp_path: Path) -> None:
    source = tmp_path / "Nested.s"
    source.write_bytes(b'"Syntax version 2.23 N"\n(* outer (* inner *) \x81 *)\n')

    text = parser_api._decode_source_bytes_for_parse(source)

    assert "\ufffd" in text


def test_undefined_byte_inside_an_unterminated_nested_comment_still_fails(tmp_path: Path) -> None:
    # The text ends with the inner `*)`, but the outer comment is still open, so
    # the undefined byte has no reliable boundary and the strict error survives.
    source = tmp_path / "Open.s"
    source.write_bytes(b'"Syntax version 2.23 N"\n(* outer (* inner \x81 *)')

    with pytest.raises(UnicodeDecodeError):
        parser_api._decode_source_bytes_for_parse(source)
