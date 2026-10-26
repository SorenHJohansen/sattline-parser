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
