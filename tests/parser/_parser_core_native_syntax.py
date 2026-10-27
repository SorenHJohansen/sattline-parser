# pyright: reportUnusedImport=false
"""Native-confirmed syntax added from the reverse-engineered workstation build.

Each case cites the native routine that settles it. The parser must accept the
shapes the compiler accepts and reject the shapes it refuses at parse time.
"""

from __future__ import annotations

import pytest

from sattline_parser.api import parse_source_text
from sattline_parser.errors import UnexpectedInput
from sattline_parser.models.ast_model import (
    Sequence,
    SFCAlternative,
    SFCCodeBlocks,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
)
from sattline_parser.models.expressions import Assignment, IfStmt, VarRef

_HEADER = (
    '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-10-26-12:00:00.000, name: NativeSyntax"\n'
)


def _module_code(body: str, *, datecode: str = "DateCode_ 1") -> str:
    return (
        _HEADER
        + f"BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION {datecode}\n"
        + "LOCALVARIABLES\n"
        + "   Flag: boolean := False;\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ModuleCode\n"
        + body
        + "ENDDEF (*BasePicture*);\n"
    )


def _sequence(body: str, *, opener: str = "SEQUENCE", closer: str = "ENDSEQUENCE") -> str:
    return (
        f"   {opener} Demo COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        f"      SEQINITSTEP Init\n"
        f"      SEQTRANSITION TrStart WAIT_FOR Flag\n"
        f"{body}"
        f"   {closer}\n"
    )


def _first_sequence(text: str) -> Sequence:
    picture = parse_source_text(_module_code(text))
    assert picture.modulecode is not None
    assert picture.modulecode.sequences
    return picture.modulecode.sequences[0]


# --- SEQTRANSITION: name and guard are optional (0070d180, 006fad30) --------


def test_unguarded_unnamed_transition_preserves_absent_guard() -> None:
    sequence = _first_sequence(
        _sequence("      SEQTRANSITION\n      SEQSTEP Done\n      SEQTRANSITION TrEnd WAIT_FOR True\n")
    )
    unguarded = [node for node in sequence.code if isinstance(node, SFCTransition) and node.name is None]
    assert len(unguarded) == 1
    assert unguarded[0].condition is None
    assert unguarded[0].fork is None


def test_unguarded_named_transition_keeps_name_and_absent_guard() -> None:
    sequence = _first_sequence(
        _sequence("      SEQTRANSITION Gate\n      SEQSTEP Done\n      SEQTRANSITION TrEnd WAIT_FOR True\n")
    )
    gated = [node for node in sequence.code if isinstance(node, SFCTransition) and node.name == "Gate"]
    assert len(gated) == 1
    assert gated[0].condition is None


def test_guarded_transition_keeps_false_guard() -> None:
    sequence = _first_sequence(
        _sequence(
            "      SEQTRANSITION Gate WAIT_FOR False\n      SEQSTEP Done\n      SEQTRANSITION TrEnd WAIT_FOR True\n"
        )
    )
    gated = [node for node in sequence.code if isinstance(node, SFCTransition) and node.name == "Gate"]
    assert gated[0].condition is False


def test_wait_for_without_expression_is_rejected() -> None:
    with pytest.raises(UnexpectedInput):
        parse_source_text(_module_code(_sequence("      SEQTRANSITION WAIT_FOR\n")))


# --- SEQFORK is a suffix of a step/transition (006f9850, 0070a100, 0070d180)


def test_transition_fork_with_break_flag() -> None:
    sequence = _first_sequence(
        _sequence(
            "      SEQSTEP Working\n"
            "      SEQTRANSITION TrCheck WAIT_FOR Flag\n"
            "         SEQFORK Working SEQBREAK\n"
            "      SEQTRANSITION TrEnd WAIT_FOR True\n"
        )
    )
    forked = [node for node in sequence.code if isinstance(node, SFCTransition) and node.name == "TrCheck"]
    assert forked[0].fork is not None
    assert forked[0].fork.targets == ("Working",)
    assert forked[0].fork.has_break is True
    assert forked[0].condition is not None


def test_step_fork_without_break_flag() -> None:
    sequence = _first_sequence(
        _sequence("      SEQSTEP Working\n         SEQFORK Working, Init\n      SEQTRANSITION TrEnd WAIT_FOR True\n")
    )
    steps = [node for node in sequence.code if isinstance(node, SFCStep) and node.name == "Working"]
    assert steps[0].fork is not None
    assert steps[0].fork.targets == ("Working", "Init")
    assert steps[0].fork.has_break is False


def test_standalone_seqbreak_is_rejected() -> None:
    with pytest.raises(UnexpectedInput):
        parse_source_text(
            _module_code(
                _sequence(
                    "      SEQSTEP Working\n"
                    "      SEQTRANSITION TrCheck WAIT_FOR Flag\n"
                    "      SEQBREAK\n"
                    "      SEQTRANSITION TrEnd WAIT_FOR True\n"
                )
            )
        )


def test_seqfork_cannot_open_a_sequence_body() -> None:
    # A fork is only ever a suffix of a host step/transition; at body start there
    # is no host, and the native readers do not list SEQFORK as a starter.
    with pytest.raises(UnexpectedInput):
        parse_source_text(
            _module_code(
                "   SEQUENCE Demo COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
                "      SEQFORK Working\n"
                "      SEQSTEP Working\n"
                "      SEQTRANSITION TrEnd WAIT_FOR True\n"
                "   ENDSEQUENCE\n"
            )
        )


def test_fork_without_target_is_rejected() -> None:
    with pytest.raises(UnexpectedInput):
        parse_source_text(_module_code(_sequence("      SEQSTEP Working\n      SEQTRANSITION SEQFORK\n")))


def test_empty_sequence_body_is_rejected() -> None:
    with pytest.raises(UnexpectedInput):
        parse_source_text(_module_code("   SEQUENCE Empty COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n   ENDSEQUENCE\n"))


def test_empty_alternative_branch_is_rejected() -> None:
    with pytest.raises(UnexpectedInput):
        parse_source_text(
            _module_code(
                _sequence(
                    "      ALTERNATIVESEQ\n"
                    "         SEQTRANSITION TrA WAIT_FOR Flag\n"
                    "      ALTERNATIVEBRANCH\n"
                    "      ENDALTERNATIVE\n"
                    "      SEQTRANSITION TrEnd WAIT_FOR True\n"
                )
            )
        )


def test_alternative_group_is_a_transition_position_node() -> None:
    sequence = _first_sequence(
        _sequence(
            "      ALTERNATIVESEQ\n"
            "         SEQTRANSITION TrA WAIT_FOR Flag\n"
            "      ALTERNATIVEBRANCH\n"
            "         SEQTRANSITION TrB WAIT_FOR Flag\n"
            "      ENDALTERNATIVE\n"
            "      SEQSTEP Done\n"
            "      SEQTRANSITION TrEnd WAIT_FOR True\n"
        )
    )
    alternatives = [node for node in sequence.code if isinstance(node, SFCAlternative)]
    assert len(alternatives) == 1
    assert len(alternatives[0].branches) == 2


# --- SUBSEQUENCE / SUBSEQSTEP names are optional (00708b40, 0070ba70) ------


def test_unnamed_subsequence_is_accepted() -> None:
    sequence = _first_sequence(
        _sequence(
            "      SUBSEQUENCE\n         SEQSTEP Inner\n         SEQTRANSITION TrInner WAIT_FOR Flag\n      ENDSUBSEQUENCE\n"
        )
    )
    assert sequence.code


def test_unnamed_substep_is_accepted() -> None:
    sequence = _first_sequence(_sequence("      SUBSEQSTEP\n         SEQSTEP Inner\n      ENDSUBSEQSTEP\n"))
    substeps = [node for node in sequence.code if isinstance(node, SFCSubsequence) and node.kind == "substep"]
    assert substeps
    assert substeps[0].name is None


# --- DateCode: optional attribute, fixed keyword (005ab1b0, 005d6170) -------


def test_module_definition_without_datecode_is_accepted() -> None:
    picture = parse_source_text(
        _module_code(_sequence("      SEQSTEP Done\n      SEQTRANSITION TrEnd WAIT_FOR True\n"), datecode="")
    )
    assert picture.datecode is None


def test_module_definition_datecode_is_preserved() -> None:
    picture = parse_source_text(
        _module_code(
            _sequence("      SEQSTEP Done\n      SEQTRANSITION TrEnd WAIT_FOR True\n"), datecode="DateCode_ 123456"
        )
    )
    assert picture.datecode == 123456


def test_bogus_datecode_keyword_is_rejected() -> None:
    with pytest.raises(UnexpectedInput):
        parse_source_text(
            _module_code(
                _sequence("      SEQSTEP Done\n      SEQTRANSITION TrEnd WAIT_FOR True\n"), datecode="Bogus_ 5"
            )
        )


def test_datecode_without_value_is_rejected() -> None:
    with pytest.raises(UnexpectedInput):
        parse_source_text(
            _module_code(
                _sequence("      SEQSTEP Done\n      SEQTRANSITION TrEnd WAIT_FOR True\n"), datecode="DateCode_"
            )
        )


def test_record_datecode_is_optional() -> None:
    source = (
        _HEADER
        + "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION\n"
        + "TYPEDEFINITIONS\n"
        + "   Plain = RECORD\n"
        + "      Value: integer;\n"
        + "   ENDDEF;\n"
        + "   Stamped = RECORD DateCode_ 7\n"
        + "      Value: integer;\n"
        + "   ENDDEF;\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    assert [definition.datecode for definition in picture.datatype_defs] == [None, 7]


# --- Statement terminators are optional (0072b660) --------------------------


def test_statements_without_semicolons_are_accepted() -> None:
    sequence = _first_sequence(
        _sequence(
            "      SEQSTEP Working\n"
            "         ENTERCODE\n"
            "            Flag = True\n"
            "            Flag = False\n"
            "      SEQTRANSITION TrEnd WAIT_FOR True\n"
        )
    )
    steps = [node for node in sequence.code if isinstance(node, SFCStep) and node.name == "Working"]
    assert len(steps[0].code.enter) == 2


def test_statements_with_semicolons_still_parse() -> None:
    sequence = _first_sequence(
        _sequence(
            "      SEQSTEP Working\n"
            "         ENTERCODE\n"
            "            Flag = True;\n"
            "            Flag = False;\n"
            "      SEQTRANSITION TrEnd WAIT_FOR True\n"
        )
    )
    steps = [node for node in sequence.code if isinstance(node, SFCStep) and code_is_empty(node.code) is False]
    assert len(steps[0].code.enter) == 2


def code_is_empty(code: SFCCodeBlocks) -> bool:
    """True when a step carries no code blocks at all."""
    return not (code.enter or code.active or code.exit)


def test_two_variable_modifiers_keep_source_order() -> None:
    # The editor rejects `OpSave Const` but compiles `State OpSave`, so the
    # source order of the modifier run is part of the AST (SL-V031 relies on it).
    source = (
        _HEADER
        + "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        + "LOCALVARIABLES\n"
        + "   Saved: integer State OpSave := 0;\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    saved = picture.localvariables[0]
    assert saved.attribute_order == ("state", "opsave")
    assert saved.state is True
    assert saved.opsave is True


def test_string_initialiser_after_a_modifier_ends_the_modifier_run() -> None:
    source = (
        _HEADER
        + "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        + "LOCALVARIABLES\n"
        + '   Message: string Secure := "text";\n'
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    message = picture.localvariables[0]
    assert message.attribute_order == ("secure",)
    assert message.init_value == "text"


def test_initial_step_accepts_a_fork_suffix() -> None:
    # 0070a100 is a caller of 006f9850 for SEQINITSTEP as well as SEQSTEP.
    sequence = _first_sequence(
        _sequence(
            "      SEQINITSTEP Rerun\n"
            "         SEQFORK TrStart\n"
            "      SEQSTEP Working\n"
            "      SEQTRANSITION TrEnd WAIT_FOR True\n"
        )
    )
    rerun = [node for node in sequence.code if isinstance(node, SFCStep) and node.name == "Rerun"]
    assert rerun[0].fork is not None
    assert rerun[0].fork.targets == ("TrStart",)


def _fork_codes(body: str) -> set[str]:
    from sattline_parser.api import parse_and_validate  # noqa: PLC0415

    _picture, diagnostics = parse_and_validate(_module_code(_sequence(body)))
    return {diagnostic.code.value for diagnostic in diagnostics}


def test_step_host_fork_must_name_a_transition() -> None:
    # 00703430: a step-hosted fork resolves to transitions, a transition-hosted
    # fork to steps. Requiring every target to be a step would be wrong.
    body = (
        "      SEQINITSTEP Rerun\n"
        "         SEQFORK Later\n"
        "      SEQSTEP Later\n"
        "      SEQTRANSITION TrEnd WAIT_FOR True\n"
    )
    assert "SL-V037" in _fork_codes(body)


def test_transition_host_fork_must_name_a_step() -> None:
    body = (
        "      SEQSTEP Working\n"
        "      SEQTRANSITION TrJump WAIT_FOR Flag\n"
        "         SEQFORK TrEnd\n"
        "      SEQTRANSITION TrEnd WAIT_FOR True\n"
    )
    assert "SL-V037" in _fork_codes(body)


def test_fork_targets_of_the_right_kind_are_clean() -> None:
    body = (
        "      SEQINITSTEP Rerun\n"
        "         SEQFORK TrStart\n"
        "      SEQTRANSITION TrMid WAIT_FOR Flag\n"
        "      SEQSTEP Working\n"
        "      SEQTRANSITION TrJump WAIT_FOR Flag\n"
        "         SEQFORK Working, Rerun\n"
        "      SEQSTEP Done\n"
        "      SEQTRANSITION TrEnd WAIT_FOR True\n"
    )
    assert _fork_codes(body) == set()


def test_fork_to_an_unknown_name_is_still_unknown_not_wrong_kind() -> None:
    body = (
        "      SEQSTEP Working\n"
        "      SEQTRANSITION TrJump WAIT_FOR Flag\n"
        "         SEQFORK Ghost\n"
        "      SEQTRANSITION TrEnd WAIT_FOR True\n"
    )
    codes = _fork_codes(body)
    assert "SL-V017" in codes
    assert "SL-V037" not in codes


def test_module_in_view_is_a_distinct_invocation_property() -> None:
    # 00665970 reads token 0xA4 with the Boolean-property reader 00631940 and
    # stores it separately from Enable_ (both may appear).
    source = (
        _HEADER
        + 'BasePicture Invocation (0.0,0.0,0.0,1.0,1.0 Module_In_View = True : OutVar_ "Visible" '
        + "Enable_ = False) : MODULEDEFINITION DateCode_ 1\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ENDDEF (*BasePicture*);\n"
    )
    header = parse_source_text(source).header
    assert header.module_in_view is True
    assert header.enable is False
    assert header.invoke_coord_tails == ["Visible"]


def test_module_in_view_rejects_on_off() -> None:
    # The Boolean-property reader takes True/False only, unlike a general
    # boolean expression where On/Off are legal primaries (00487a60).
    source = (
        _HEADER
        + "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0 Module_In_View = On) : MODULEDEFINITION DateCode_ 1\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ENDDEF (*BasePicture*);\n"
    )
    with pytest.raises(UnexpectedInput):
        parse_source_text(source)


def test_equations_keyword_is_accepted_like_equationblock() -> None:
    # 00726030 accepts both spellings and flags them differently; we keep the
    # parsed shape identical until the flag's downstream meaning is recovered.
    source = (
        _HEADER
        + "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        + "LOCALVARIABLES\n"
        + "   Flag: boolean := False;\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ModuleCode\n"
        + "   EQUATIONS Eq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        + "      Flag = True\n"
        + "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    module_code = picture.modulecode
    assert module_code is not None
    assert [equation.name for equation in module_code.equations or []] == ["Eq"]


# --- keyword case insensitivity (00626850 / 0062e3d0) -----------------------


def test_keyword_terminals_are_case_insensitive() -> None:
    from sattline_parser.grammar.keywords import make_keywords_case_insensitive  # noqa: PLC0415

    text = 'FOO.10: "Foo"\nSEMI: ";"\nBAR: /Ba+r/\nBAZ: /(?i:Quux)/\n'
    assert make_keywords_case_insensitive(text) == (
        'FOO.10: /(?i:Foo\\b)/\nSEMI: ";"\nBAR: /(?i:Ba+r)/\nBAZ: /(?i:Quux)/\n'
    )


def test_lowercase_keywords_parse_like_canonical_case() -> None:
    canonical = (
        _HEADER
        + "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        + "LOCALVARIABLES\n"
        + "   Counter: integer State := 0;\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "ModuleCode\n"
        + "   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        + "      Counter = Counter + 1;\n"
        + "ENDDEF (*BasePicture*);\n"
    )
    lowered = canonical.replace("BasePicture", "basepicture").replace("MODULEDEFINITION", "moduledefinition")
    lowered = (
        lowered.replace("LOCALVARIABLES", "localvariables")
        .replace("ModuleDef", "moduledef")
        .replace("ClippingBounds", "clippingbounds")
        .replace("ModuleCode", "modulecode")
        .replace("EQUATIONBLOCK", "equationblock")
        .replace("COORD", "coord")
        .replace("OBJSIZE", "objsize")
        .replace("ENDDEF", "enddef")
        .replace("DateCode_", "datecode_")
    )
    canonical_picture = parse_source_text(canonical)
    lowered_picture = parse_source_text(lowered)
    assert lowered_picture.name == canonical_picture.name
    assert lowered_picture.localvariables[0].name == "Counter"
    assert lowered_picture.datecode == canonical_picture.datecode == 1


def test_lowercase_boolean_and_state_suffix_are_equivalent() -> None:
    source = (
        _HEADER
        + "basepicture Invocation (0.0,0.0,0.0,1.0,1.0) : moduledefinition datecode_ 1\n"
        + "localvariables\n"
        + "   Counter: integer state := 0;\n"
        + "   Mirror: integer := 0;\n"
        + "moduledef\nclippingbounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "modulecode\n"
        + "   equationblock Main coord 0.0, 0.0 objsize 1.0, 1.0 :\n"
        + "      if true then\n"
        + "         Mirror = Counter:old;\n"
        + "      endif\n"
        + "enddef (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    module_code = picture.modulecode
    assert module_code is not None
    equation = (module_code.equations or [])[0]
    statement = equation.code[0]
    assert isinstance(statement, IfStmt)
    nested = statement.branches[0][1][0]
    assert isinstance(nested, Assignment)
    reference = nested.value
    assert isinstance(reference, VarRef)
    assert reference.state == "old"


def test_lowercase_seq_control_flags_are_detected() -> None:
    source = _module_code(
        "   sequence Demo (seqcontrol, seqtimer) coord 0.0, 0.0 objsize 1.0, 1.0\n"
        "      seqstep Only\n"
        "      seqtransition End wait_for true\n"
        "   endsequence\n"
    )
    picture = parse_source_text(source)
    module_code = picture.modulecode
    assert module_code is not None
    sequence = (module_code.sequences or [])[0]
    assert sequence.seqcontrol is True
    assert sequence.seqtimer is True
    assert sequence.type == "SEQUENCE"


def test_equation_block_without_name_or_metadata() -> None:
    # 00726030: keyword, optional name, optional coord/size, optional layer, ':'
    source = _module_code(
        "   EQUATIONBLOCK :\n"
        "      Flag = True\n"
        "   EQUATIONS Named :\n"
        "      Flag = False\n"
        "   EQUATIONBLOCK Located COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "      Flag = True\n"
    )
    picture = parse_source_text(source)
    module_code = picture.modulecode
    assert module_code is not None
    equations = module_code.equations or []
    assert [equation.name for equation in equations] == [None, "Named", "Located"]
    assert equations[0].position is None and equations[0].size is None
    assert equations[2].position == (0.0, 0.0)
    assert len(equations[0].code) == 1
