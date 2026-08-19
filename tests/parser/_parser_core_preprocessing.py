# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false, reportUnknownArgumentType=false, reportCallIssue=false, reportUnknownMemberType=false
# ruff: noqa: F403, F405
from sattline_parser.preprocessing import is_compressed
from sattline_parser.preprocessing.compressed import (
    _COMPAT_TRANSFORMS,
    _GRAPHOBJECTS_ENDDEF_RE,
    _MARKER_RE,
    _SEMI_BEFORE_ASSIGN_RE,
    SEED_MAPPING,
    CompatTransform,
    NormalizationKind,
    _align_replacement,
    _decode_markers,
    _decode_with_map,
    _normalize_compat,
    _regex_sub,
)
from sattline_parser.source_document import GENERATED, Generated

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


# ---------------------------------------------------------------------------
# Compatibility transform catalog
# ---------------------------------------------------------------------------


def test_compat_transform_catalog_entries_are_documented_and_categorized():
    names = [transform.name for transform in _COMPAT_TRANSFORMS]
    assert len(names) == len(set(names))
    for transform in _COMPAT_TRANSFORMS:
        assert isinstance(transform, CompatTransform)
        assert transform.name
        assert transform.description
        assert transform.kind in (
            NormalizationKind.SYNTAX_REPAIR,
            NormalizationKind.SEMANTIC_REPAIR,
            NormalizationKind.GRAMMAR_COMPAT,
        )
        assert transform.pattern.pattern


def test_compat_transform_catalog_marks_all_semantic_repairs():
    semantic = {
        transform.name for transform in _COMPAT_TRANSFORMS if transform.kind is NormalizationKind.SEMANTIC_REPAIR
    }
    assert semantic == {
        "empty_assign_default",
        "duration_str_value",
        "time_str_value",
        "date_timestamp_value",
        "equationblock_modulecode",
        "empty_trailing_arg",
    }


def test_compat_transform_catalog_documents_empty_trailing_arg_semantics():
    transform = _COMPAT_TRANSFORMS[-1]
    assert transform.name == "empty_trailing_arg"
    assert transform.kind is NormalizationKind.SEMANTIC_REPAIR
    assert "Func(a, )" in transform.description
    assert "Func(a, 0)" in transform.description


# ---------------------------------------------------------------------------
# Golden normalization outputs
# ---------------------------------------------------------------------------


def test_normalize_compat_golden_semantic_repairs():
    golden = [
        ("X := ;", "X := Default;"),
        ("X := Func(a, )", "X := Func(a, 0)"),
        (
            "EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :",
            "ModuleCode EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :",
        ),
        ('duration := "5s";', 'duration := Duration_Value "5s";'),
        ('time := "6s";', 'time := Time_Value "6s";'),
        ('=> "2024-01-02-03:04:05.678"', '=> Time_Value "2024-01-02-03:04:05.678"'),
    ]
    for raw, expected in golden:
        decoded, _char_map = _decode_with_map(raw, dict(SEED_MAPPING))
        assert decoded == expected


def test_normalize_compat_golden_syntax_repairs():
    golden = [
        ("X := 1; ENDDEF;", "X := 1; ENDDEF"),
        ("X; := 1", "X := 1"),
        ("IF x THEN y ENDIF; ,", "IF x THEN y ENDIF,"),
        ("IF x THEN y ENDIF; )", "IF x THEN y ENDIF)"),
        ("IF x THEN y ENDIF", "IF x THEN y ENDIF;"),
        ("ExecuteLocalOld = ExecuteLocal:Old ENDDEF", "ExecuteLocalOld = ExecuteLocal:Old; ENDDEF"),
        ("ExecuteState:Old IF x THEN y ENDIF", "ExecuteState:Old; IF x THEN y ENDIF;"),
        ("GraphObjects : ENDDEF", "ENDDEF"),
        ("integer ENDDEF", "integer ; ENDDEF"),
        ("GraphObjects : InteractObjects", "InteractObjects"),
    ]
    for raw, expected in golden:
        decoded, _char_map = _decode_with_map(raw, dict(SEED_MAPPING))
        assert decoded == expected


def test_normalize_compat_golden_grammar_compat_spellings():
    golden = [
        ("Enable_ = Flag : OutVar_", "Enable_ = Flag : InVar_"),
        ("SomeVar := TrueVar", "SomeVar := TTrueVar"),
        ("TrueVar", "TTrueVar"),
    ]
    for raw, expected in golden:
        decoded, _char_map = _decode_with_map(raw, dict(SEED_MAPPING))
        assert decoded == expected


# ---------------------------------------------------------------------------
# Generated-text provenance (first-class distinction)
# ---------------------------------------------------------------------------


def test_generated_provenance_is_a_first_class_int_like_sentinel():
    assert type(GENERATED) is Generated
    assert isinstance(GENERATED, int)
    assert GENERATED == -1
    assert GENERATED < 0
    assert repr(GENERATED) == "GENERATED"


def test_regex_sub_generated_char_never_claims_a_real_source_position():
    decoded, char_map = _regex_sub(
        "A GraphObjects : ENDDEF B",
        list(range(25)),
        _GRAPHOBJECTS_ENDDEF_RE,
        "ENDDEF",
    )
    assert decoded == "A ENDDEF B"
    start = decoded.index("ENDDEF")
    assert char_map[start : start + 6] == [17, 18, 19, 20, 21, 22]


def test_regex_sub_aligns_rewritten_text_to_surviving_source_chars():
    decoded, char_map = _regex_sub("X; :=Y", list(range(6)), _SEMI_BEFORE_ASSIGN_RE, " :=")
    assert decoded == "X :=Y"
    assert char_map == [0, 2, 3, 4, 5]


def test_regex_sub_marker_expansion_keeps_real_suffix_aligned():
    decoded, char_map = _regex_sub("#0<Remark", list(range(9)), _MARKER_RE, lambda m: "* " + m.group(0)[3:])
    assert decoded == "* Remark"
    assert char_map == [GENERATED, GENERATED, 3, 4, 5, 6, 7, 8]


def test_decode_injected_semantic_text_is_first_class_generated():
    decoded, char_map = _decode_with_map("X := Func(a, )", dict(SEED_MAPPING))
    assert decoded == "X := Func(a, 0)"
    zero_idx = decoded.index("0")
    assert type(char_map[zero_idx]) is Generated
    assert char_map[zero_idx] == GENERATED
    assert char_map[decoded.index(")")] == 13


def test_decode_injected_default_value_is_first_class_generated():
    decoded, char_map = _decode_with_map("X := ;", dict(SEED_MAPPING))
    assert decoded == "X := Default;"
    default_idx = decoded.index("Default")
    for i in range(default_idx, default_idx + len("Default")):
        assert isinstance(char_map[i], Generated)
    assert char_map[decoded.index(";")] == 5


def test_align_replacement_edge_cases():
    assert _align_replacement("", "abc", [0, 1, 2]) == []
    assert _align_replacement("x", "abc", [0, 1, 2]) == [GENERATED]
    assert _align_replacement("ENDIF;", "ENDIF", [0, 1, 2, 3, 4]) == [0, 1, 2, 3, 4, GENERATED]
    assert _align_replacement("axc", "abc", [0, 1, 2]) == [0, GENERATED, 2]


# ---------------------------------------------------------------------------
# End-to-end semantic verification
# ---------------------------------------------------------------------------


def test_empty_trailing_arg_injection_is_visible_in_the_ast():
    from sattline_parser.models.expressions import Assignment, FuncCall, VarRef  # noqa: PLC0415

    src = (
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "    Y: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "        Y = Func(a, );\n"
        "ENDDEF (*BasePicture*);\n"
    )
    decoded, _mapping = preprocess_sl_text(src)
    assert "Y = Func(a, 0);" in decoded

    bp = parser_core_parse_source_text(decoded)
    modulecode = bp.modulecode
    assert modulecode is not None
    equations = modulecode.equations
    assert equations is not None
    statement = equations[0].code[0]
    assert isinstance(statement, Assignment)
    value = statement.value
    assert isinstance(value, FuncCall)
    assert value.name == "Func"
    arg_a, arg_zero = value.args
    assert isinstance(arg_a, VarRef)
    assert arg_a.name == "a"
    assert arg_zero == 0
