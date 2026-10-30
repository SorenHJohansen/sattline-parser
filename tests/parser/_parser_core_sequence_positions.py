# pyright: reportUnusedImport=false
"""Sequence position rules (S/T/M productions) at parse+validate level.

Each rejected shape below is one the real tool refuses: the probes that produced
them are named in the test, so a future weakening is visible.
"""

from __future__ import annotations

from typing import Any

from sattline_parser.api import parse_and_validate
from sattline_parser.validation.diagnostics import DiagnosticCode

_HEADER = (
    '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-10-26-12:00:00.000, name: SeqPositions"\n'
    "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
    "LOCALVARIABLES\n"
    "   Flag: boolean := False;\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ModuleCode\n"
)

_FOOTER = "ENDDEF (*BasePicture*);\n"


def _diagnostics(body: str) -> tuple[Any, ...]:
    source = _HEADER + body + _FOOTER
    _picture, diagnostics = parse_and_validate(source)
    # Every finding must be locatable: a message without a span forces a search.
    for diagnostic in diagnostics:
        assert diagnostic.span is not None, diagnostic.message
    return diagnostics


def _codes(body: str) -> set[str]:
    return {diagnostic.code.value for diagnostic in _diagnostics(body)}


def _sequence(body: str, *, opener: str = "SEQUENCE", closer: str = "ENDSEQUENCE") -> str:
    return f"   {opener} Demo COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n{body}   {closer}\n"


_STEP = "      SEQSTEP S{n}\n"
_TRANSITION = "      SEQTRANSITION T{n} WAIT_FOR Flag\n"


def test_closed_body_requires_step_before_transition() -> None:
    # Probe EdgeSeqAlt.x: ALTERNATIVESEQ immediately after a transition.
    body = _sequence(
        _STEP.format(n=1)
        + _TRANSITION.format(n=1)
        + "      ALTERNATIVESEQ\n"
        + "         SEQTRANSITION Ta WAIT_FOR Flag\n"
        + "      ALTERNATIVEBRANCH\n"
        + "         SEQTRANSITION Tb WAIT_FOR Flag\n"
        + "      ENDALTERNATIVE\n"
        + _TRANSITION.format(n=2)
    )
    assert DiagnosticCode.SEQUENCE_POSITION_INVALID.value in _codes(body)


def test_closed_body_rejects_consecutive_steps() -> None:
    body = _sequence(_STEP.format(n=1) + _STEP.format(n=2) + _TRANSITION.format(n=1))
    assert DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS.value in _codes(body)


def test_closed_body_must_not_end_with_step() -> None:
    body = _sequence(_STEP.format(n=1) + _TRANSITION.format(n=1) + _STEP.format(n=2))
    assert DiagnosticCode.SEQUENCE_ENDS_WITH_STEP.value in _codes(body)


def test_alternative_branch_must_start_with_transition() -> None:
    body = _sequence(
        _STEP.format(n=1)
        + "      ALTERNATIVESEQ\n"
        + _STEP.format(n=2)
        + _TRANSITION.format(n=1)
        + "      ALTERNATIVEBRANCH\n"
        + _TRANSITION.format(n=2)
        + "      ENDALTERNATIVE\n"
        + _STEP.format(n=3)
        + _TRANSITION.format(n=3)
    )
    assert DiagnosticCode.SFC_ALTERNATIVE_BRANCH_START.value in _codes(body)


def test_alternative_branch_must_not_end_with_step() -> None:
    # Probe ValidSubSeqTransB.x: branch 1 is TRANSITION, STEP, then the next
    # ALTERNATIVEBRANCH; the tool reports "Incorrect Syntax - Error 32" there.
    body = _sequence(
        _STEP.format(n=1)
        + "      ALTERNATIVESEQ\n"
        + _TRANSITION.format(n=2)
        + _STEP.format(n=2)
        + "      ALTERNATIVEBRANCH\n"
        + _TRANSITION.format(n=3)
        + _STEP.format(n=3)
        + _TRANSITION.format(n=4)
        + "      ENDALTERNATIVE\n"
        + _STEP.format(n=4)
        + _TRANSITION.format(n=5)
    )
    assert DiagnosticCode.SEQUENCE_POSITION_INVALID.value in _codes(body)


def test_parallel_branch_must_start_with_step() -> None:
    body = _sequence(
        _STEP.format(n=1)
        + _TRANSITION.format(n=1)
        + "      PARALLELSEQ\n"
        + _TRANSITION.format(n=2)
        + "      PARALLELBRANCH\n"
        + _STEP.format(n=2)
        + "      ENDPARALLEL\n"
        + _TRANSITION.format(n=3)
    )
    assert DiagnosticCode.SFC_PARALLEL_BRANCH_START.value in _codes(body)


def test_parallel_branch_must_end_with_step() -> None:
    body = _sequence(
        _STEP.format(n=1)
        + _TRANSITION.format(n=1)
        + "      PARALLELSEQ\n"
        + _STEP.format(n=2)
        + _TRANSITION.format(n=2)
        + "      PARALLELBRANCH\n"
        + _STEP.format(n=3)
        + "      ENDPARALLEL\n"
        + _TRANSITION.format(n=3)
    )
    assert DiagnosticCode.SFC_PARALLEL_BRANCH_START.value in _codes(body)


def test_parallel_branch_may_interleave_structural_items() -> None:
    body = _sequence(
        _STEP.format(n=1)
        + _TRANSITION.format(n=1)
        + "      PARALLELSEQ\n"
        + "         SUBSEQUENCE Inner\n"
        + _STEP.format(n=2)
        + _TRANSITION.format(n=2)
        + "         ENDSUBSEQUENCE\n"
        + _STEP.format(n=3)
        + "      PARALLELBRANCH\n"
        + _STEP.format(n=4)
        + "      ENDPARALLEL\n"
        + _STEP.format(n=5)
        + _TRANSITION.format(n=3)
    )
    assert DiagnosticCode.SEQUENCE_POSITION_INVALID.value not in _codes(body)


def test_open_sequence_may_stop_on_a_step() -> None:
    body = _sequence(_STEP.format(n=1), opener="OPENSEQUENCE", closer="ENDOPENSEQUENCE")
    assert DiagnosticCode.SEQUENCE_ENDS_WITH_STEP.value not in _codes(body)
    assert DiagnosticCode.SEQUENCE_POSITION_INVALID.value not in _codes(body)


def test_open_sequence_rejects_two_transitions_in_a_row() -> None:
    body = _sequence(
        _TRANSITION.format(n=1) + _TRANSITION.format(n=2),
        opener="OPENSEQUENCE",
        closer="ENDOPENSEQUENCE",
    )
    assert DiagnosticCode.SEQUENCE_POSITION_INVALID.value in _codes(body)


def test_substep_body_is_step_led() -> None:
    body = _sequence(
        _STEP.format(n=1)
        + _TRANSITION.format(n=1)
        + "      SUBSEQSTEP Inner\n"
        + _TRANSITION.format(n=2)
        + "      ENDSUBSEQSTEP\n"
        + "      SEQSTEP Done\n"
        + _TRANSITION.format(n=3)
    )
    assert DiagnosticCode.SFC_PARALLEL_BRANCH_START.value in _codes(body)


def test_subsequence_body_is_closed() -> None:
    body = _sequence(
        _STEP.format(n=1)
        + "      SUBSEQUENCE Inner\n"
        + _STEP.format(n=2)
        + "      ENDSUBSEQUENCE\n"
        + _TRANSITION.format(n=1)
    )
    assert DiagnosticCode.SEQUENCE_ENDS_WITH_STEP.value in _codes(body)


def test_sub_transition_body_is_transition_led() -> None:
    body = _sequence(
        _STEP.format(n=1)
        + "      SUBSEQTRANSITION Inner\n"
        + _STEP.format(n=2)
        + _TRANSITION.format(n=2)
        + "      ENDSUBSEQTRANSITION\n"
        + _STEP.format(n=3)
        + _TRANSITION.format(n=3)
    )
    assert DiagnosticCode.SFC_ALTERNATIVE_BRANCH_START.value in _codes(body)


def test_a_clean_sequence_reports_nothing() -> None:
    body = _sequence(_STEP.format(n=1) + _TRANSITION.format(n=1) + _STEP.format(n=2) + _TRANSITION.format(n=2))
    assert _codes(body) == set()


# --- hand-built AST coverage: shapes the grammar cannot produce ---------------
#
# The grammar already refuses empty bodies, so these paths are only reachable
# from a programmatically built AST (consumer code, cached payloads, tests).
# They still have to report the same findings rather than silently passing.

from sattline_parser.models.ast_model import (  # noqa: E402
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCCodeBlocks,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
)
from sattline_parser.validation.diagnostics import Diagnostic  # noqa: E402
from sattline_parser.validation.sequences import check_sequence_positions  # noqa: E402

_SEQ_TYPE = "SEQUENCE"
_OPEN_TYPE = "OPENSEQUENCE"


def _step() -> SFCStep:
    return SFCStep(kind="step", name=None, code=SFCCodeBlocks())


def _tr() -> SFCTransition:
    return SFCTransition(name=None, condition=None)


def _sub(kind: str) -> SFCSubsequence:
    body: list[SFCBodyItem] = [_step(), _tr()] if kind == "sequence" else [_step()]
    return SFCSubsequence(name=None, body=body, kind=kind)


def _position_codes(*items: SFCBodyItem, type_: str = _SEQ_TYPE) -> list[str]:
    sequence = Sequence(name="S", type=type_, position=(0.0, 0.0), size=(1.0, 1.0), code=list(items))
    errors: list[Diagnostic] = []
    check_sequence_positions([sequence], errors)
    return [error.code.value for error in errors]


def test_empty_bodies_report_a_position_error() -> None:
    for type_ in (_SEQ_TYPE, _OPEN_TYPE):
        assert "SL-V036" in _position_codes(type_=type_)
    # empty alternative branch, sub-transition body, parallel branch and sub-step
    assert "SL-V036" in _position_codes(SFCAlternative(branches=[[]]), _tr())
    assert "SL-V036" in _position_codes(SFCTransitionSub(name=None, body=[]), _tr())
    assert "SL-V036" in _position_codes(SFCParallel(branches=[[]]), _tr())
    assert "SL-V036" in _position_codes(SFCSubsequence(name=None, body=[], kind="substep"), _tr())


def test_transition_bodies_reject_step_jumbles() -> None:
    # two transitions in a row inside a branch
    assert "SL-V036" in _position_codes(SFCAlternative(branches=[[_tr(), _tr()]]), _tr())
    # consecutive steps inside a branch
    assert "SL-V016" in _position_codes(SFCAlternative(branches=[[_tr(), _step(), _step()]]), _tr())
    # a structural item between a branch step and its transition
    assert "SL-V036" in _position_codes(
        SFCAlternative(branches=[[_tr(), _step(), _sub("sequence")]]),
        _tr(),
    )


def test_step_bodies_reject_transition_jumbles() -> None:
    # consecutive steps
    assert "SL-V016" in _position_codes(SFCParallel(branches=[[_step(), _step()]]), _tr())
    # structural item between a step and its transition
    assert "SL-V036" in _position_codes(SFCParallel(branches=[[_step(), _sub("sequence")]]), _tr())
    # structural item after a transition is allowed, a second transition is not
    assert "SL-V036" in _position_codes(
        SFCParallel(branches=[[_step(), _tr(), _sub("sequence"), _tr()]]),
        _tr(),
    )
    assert _position_codes(SFCParallel(branches=[[_step(), _tr(), _sub("sequence"), _step()]]), _tr()) == []


def test_closed_body_rejects_structural_after_step() -> None:
    assert "SL-V036" in _position_codes(_step(), _sub("sequence"), _tr())


def test_open_body_states_are_covered() -> None:
    # step then step, and step then a structural item
    assert "SL-V016" in _position_codes(_step(), _step(), type_=_OPEN_TYPE)
    assert "SL-V036" in _position_codes(_step(), _sub("sequence"), type_=_OPEN_TYPE)
    # boundary state: a structural item is fine, a second transition is not
    assert _position_codes(_tr(), _sub("sequence"), type_=_OPEN_TYPE) == []
    assert "SL-V036" in _position_codes(_tr(), _sub("sequence"), _tr(), type_=_OPEN_TYPE)


def test_position_diagnostics_point_at_the_offending_element() -> None:
    body = _sequence(_STEP.format(n=1) + _STEP.format(n=2) + _TRANSITION.format(n=1))
    source = _HEADER + body + _FOOTER
    _picture, diagnostics = parse_and_validate(source)

    [diagnostic] = [finding for finding in diagnostics if finding.code is DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS]
    assert diagnostic.span is not None
    line_text = source.splitlines()[diagnostic.span.line - 1]
    assert "SEQSTEP S2" in line_text


def test_nested_body_participates_in_name_and_fork_checks() -> None:
    # A name inside a nested body is still a module-level SFC name.
    duplicate = _sequence(
        "      SUBSEQUENCE Nested\n"
        "         SEQSTEP Dup\n"
        "         SEQTRANSITION T1 WAIT_FOR Flag\n"
        "      ENDSUBSEQUENCE\n" + _STEP.format(n="1").replace("S1", "Dup") + _TRANSITION.format(n=2)
    )
    assert DiagnosticCode.DUPLICATE_SFC_ELEMENT_NAME.value in _codes(duplicate)

    # A SEQFORK inside a nested body resolves against the same element table.
    unknown = _sequence(
        "      SUBSEQUENCE Nested\n"
        "         SEQSTEP Forked SEQFORK MissingTarget\n"
        "         SEQTRANSITION T1 WAIT_FOR Flag\n"
        "      ENDSUBSEQUENCE\n" + _STEP.format(n=1) + _TRANSITION.format(n=2)
    )
    assert DiagnosticCode.SEQUENCE_FORK_UNKNOWN_TARGET.value in _codes(unknown)

    wrong_kind = _sequence(
        "      SUBSEQUENCE Nested\n"
        "         SEQSTEP Forked SEQFORK S1\n"
        "         SEQTRANSITION T1 WAIT_FOR Flag\n"
        "      ENDSUBSEQUENCE\n" + _STEP.format(n=1) + _TRANSITION.format(n=2)
    )
    assert DiagnosticCode.SEQUENCE_FORK_TARGET_KIND.value in _codes(wrong_kind)
