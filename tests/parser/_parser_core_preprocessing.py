# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false, reportUnknownArgumentType=false, reportCallIssue=false, reportUnknownMemberType=false
# ruff: noqa: F403, F405
from sattline_parser.preprocessing import is_compressed
from sattline_parser.preprocessing.compressed import (
    _COMPAT_TRANSFORMS,
    _MARKER_RE,
    SEED_MAPPING,
    _align_replacement,
    _decode_markers,
    _decode_with_map,
    _header_compression_flag,
    _normalize_compat,
    _regex_sub,
)
from sattline_parser.source_document import GENERATED, Generated

from ._parser_core_test_support import *


def test_is_compressed_ignores_markers_inside_comments():
    src = "(* signal tags: #aa #bb #cc #dd #ee #ff #gg #hh #ii #jj #kk #ll #mm #nn *)\nMODULEDEFINITION Demo\nENDDEF\n"

    assert is_compressed(src) is False


def test_is_compressed_ignores_markers_inside_strings():
    src = 'MODULEDEFINITION Demo\nENDDEF\nSomeVar := "tags #aa #bb #cc #dd #ee #ff #gg #hh #ii #jj";\n'

    assert is_compressed(src) is False


def test_is_compressed_still_detects_structural_markers_when_strings_contain_markers():
    src = " ".join(["#01X"] * 10) + ' "tags #aa #bb #cc #dd #ee #ff #gg #hh #ii #jj"'

    assert is_compressed(src) is True


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

    registry, decoded, char_map = _decode_markers(text, dict(SEED_MAPPING))
    normalized, norm_map = _normalize_compat(registry, decoded, char_map)
    restored, restored_map = registry.restore(normalized, norm_map)
    full_decoded, full_map = _decode_with_map(text, dict(SEED_MAPPING))

    assert restored == full_decoded
    assert tuple(restored_map) == tuple(full_map)
    assert len(norm_map) == len(normalized)


def test_decode_markers_stage_protects_strings_from_unknown_markers():
    text = '#71 Demo ENDDEF "text #99 unknown"'

    registry, _decoded, _char_map = _decode_markers(text, dict(SEED_MAPPING))
    normalized, _norm_map = _normalize_compat(registry, _decoded, _char_map)
    restored, _restored_map = registry.restore(normalized, _norm_map)

    assert '"text #99 unknown"' in restored


# ---------------------------------------------------------------------------
# Compatibility transform catalog
# ---------------------------------------------------------------------------


def test_compat_transform_catalog_is_empty():
    assert len(_COMPAT_TRANSFORMS) == 0


def test_seed_mapping_expands_marker_70_to_composite_object():
    assert SEED_MAPPING["#70"] == "CompositeObject"


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
