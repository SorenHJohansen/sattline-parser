# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from sattline_parser.preprocessing import is_compressed
from sattline_parser.preprocessing.compressed import (
    SEED_MAPPING,
    _decode_markers,
    _decode_with_map,
    _normalize_compat,
)

from ._parser_core_test_support import *


def test_preprocess_sl_text_injects_modulecode_before_equationblock_when_missing():
    decoded, mapping = preprocess_sl_text("MODULEDEFINITION Demo EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :")

    assert "MODULEDEFINITION Demo ModuleCode EQUATIONBLOCK Main" in decoded
    assert mapping["#84"] == "ModuleCode"


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
        'duration := "5s"; => "2024-01-02-03:04:05.678" '
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


def test_normalize_compat_stage_repairs_only_decoded_text_not_string_content():
    text = 'ENDIF GraphObjects : InteractObjects "ENDIF GraphObjects : InteractObjects"'

    registry, decoded, char_map = _decode_markers(text, dict(SEED_MAPPING))
    normalized, _norm_map = _normalize_compat(registry, decoded, char_map)
    restored, _restored_map = registry.restore(normalized, _norm_map)

    assert restored == 'ENDIF; InteractObjects "ENDIF GraphObjects : InteractObjects"'
