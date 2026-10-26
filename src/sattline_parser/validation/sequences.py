"""Sequence element-position validation (native S/T/M productions).

The native SattLine readers classify every sequence construct into exactly one
position and accept only specific interleavings (`00625d20` initialises the
three starter sets; `00708d20`, `007089a0`, `0070db70`, `0070be80`, `0070bcb0`,
`0070b440`, `0070cf20` implement the readers):

===================  ==========================================================
position             constructs
===================  ==========================================================
``S`` (step)         ``SEQINITSTEP``, ``SEQSTEP``, ``SUBSEQSTEP``, ``PARALLELSEQ``
``T`` (transition)   ``SEQTRANSITION``, ``SUBSEQTRANSITION``, ``ALTERNATIVESEQ``
``M`` (structural)   ``SUBSEQUENCE``
===================  ==========================================================

The accepted body shapes are::

    closed_body     = (S T | M)+          SEQUENCE, SUBSEQUENCE
    transition_body = T (S T | M)*        each ALTERNATIVEBRANCH, SUBSEQTRANSITION
    step_body       = M* S (T M* S)*      each PARALLELBRANCH, SUBSEQSTEP
    open_body       = S after_step
                    | T after_boundary
                    | M after_boundary    OPENSEQUENCE
    after_step      = empty | T after_boundary
    after_boundary  = empty | M after_boundary | S after_step

The real tool enforces these at parse time (surfacing as ``EngLoopSeqSym
Expected``/``EndLoopSeqSym Expected``/``Incorrect Syntax``). We enforce them
after the parse so comments may appear anywhere, and report ``SL-V016``,
``SL-V023``, ``SL-V024``, ``SL-V033`` or ``SL-V036`` accordingly.

``SEQFORK`` occupies no position: it is a suffix of its host step/transition
(`006f9850`, `0070a100`, `0070d180`) and therefore never appears here.
"""

from __future__ import annotations

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    CodeComment,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
)
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode

__all__ = ["check_sequence_positions"]

STEP = "S"
TRANSITION = "T"
STRUCTURAL = "M"

CLOSED = "closed"
TRANSITION_BODY = "transition"
STEP_BODY = "step"
OPEN = "open"


def _position(item: SFCBodyItem) -> str | None:
    """Classify a sequence element; ``None`` for comments."""
    if isinstance(item, CodeComment):
        return None
    if isinstance(item, SFCStep | SFCParallel):
        return STEP
    if isinstance(item, SFCTransition | SFCTransitionSub | SFCAlternative):
        return TRANSITION
    # The union is exhausted down to SFCSubsequence here.
    return STEP if item.kind == "substep" else STRUCTURAL
    # Defensive: an unknown node cannot be positioned, so treat it as structural
    # rather than silently splitting a step/transition pair.
    return STRUCTURAL


def _elements(items: list[SFCBodyItem]) -> list[str]:
    positions: list[str] = []
    for item in items:
        position = _position(item)
        if position is not None:
            positions.append(position)
    return positions


def _error(code: DiagnosticCode, message: str) -> Diagnostic:
    return Diagnostic(code=code, message=message, span=None)


def _consecutive_steps() -> Diagnostic:
    return _error(
        DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS,
        "Consecutive SFC steps without an intervening SEQTRANSITION",
    )


def _structural_after_step() -> Diagnostic:
    return _error(
        DiagnosticCode.SEQUENCE_POSITION_INVALID,
        "A SUBSEQUENCE cannot appear between a SEQSTEP and its SEQTRANSITION",
    )


def _step_before_transition(position: str) -> Diagnostic:
    detail = "a structural construct" if position == STRUCTURAL else "another transition"
    return _error(
        DiagnosticCode.SEQUENCE_POSITION_INVALID,
        f"Expected a SEQSTEP before this element, found {detail}; steps and transitions must alternate",
    )


def _step_expected(position: str) -> Diagnostic:
    detail = "a transition" if position == TRANSITION else "a structural construct"
    return _error(
        DiagnosticCode.SEQUENCE_POSITION_INVALID,
        f"Expected a SEQSTEP before this element, found {detail}",
    )


def check_sequence_positions(sequences: list[Sequence] | None, errors: list[Diagnostic]) -> None:
    """Validate every sequence body and its nested branch/subsequence bodies."""
    for sequence in sequences or ():
        is_open = sequence.type == const.GRAMMAR_VALUE_OPENSEQUENCE
        _check_body(sequence.code, OPEN if is_open else CLOSED, errors)


def _check_body(items: list[SFCBodyItem], shape: str, errors: list[Diagnostic]) -> None:
    if shape == CLOSED:
        _check_closed(items, errors)
    elif shape == TRANSITION_BODY:
        _check_transition_body(items, errors)
    elif shape == OPEN:
        _check_open(items, errors)
    else:
        _check_step_body(items, errors)
    _check_nested(items, errors)


def _check_nested(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """Recurse into branches and sub-bodies, each with its own body shape."""
    for item in items:
        if isinstance(item, SFCAlternative):
            for branch in item.branches:
                _check_body(branch, TRANSITION_BODY, errors)
        elif isinstance(item, SFCParallel):
            for branch in item.branches:
                _check_body(branch, STEP_BODY, errors)
        elif isinstance(item, SFCTransitionSub):
            _check_body(item.body, TRANSITION_BODY, errors)
        elif isinstance(item, SFCSubsequence):
            _check_body(item.body, CLOSED if item.kind == "sequence" else STEP_BODY, errors)


def _check_closed(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``(S T | M)+``: units alternate and the body ends after a T or an M."""
    positions = _elements(items)
    if not positions:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "A sequence body must contain at least one step/transition pair or structural construct",
            )
        )
        return
    expecting_unit = True
    for position in positions:
        if expecting_unit:
            if position == STEP:
                expecting_unit = False
            elif position == TRANSITION:
                errors.append(_step_before_transition(position))
            continue
        if position == TRANSITION:
            expecting_unit = True
            continue
        if position == STEP:
            errors.append(_consecutive_steps())
            continue
        errors.append(_structural_after_step())
    if not expecting_unit:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_ENDS_WITH_STEP,
                "A sequence must not end with a step; it must end with a SEQTRANSITION before ENDSEQUENCE",
            )
        )


def _check_transition_body(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``T (S T | M)*``: alternative branches and SUBSEQTRANSITION bodies."""
    positions = _elements(items)
    if not positions:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "An alternative branch or sub-transition must contain at least one SEQTRANSITION",
            )
        )
        return
    first = positions[0]
    if first != TRANSITION:
        errors.append(
            _error(
                DiagnosticCode.SFC_ALTERNATIVE_BRANCH_START,
                "Each ALTERNATIVESEQ branch must start with a SEQTRANSITION or a nested structure",
            )
        )
    state = "unit" if first == TRANSITION else ("after_step" if first == STEP else "unit")
    for position in positions[1:]:
        if state == "unit":
            if position == STEP:
                state = "after_step"
            elif position == TRANSITION:
                errors.append(_step_before_transition(position))
            continue
        if position == TRANSITION:
            state = "unit"
            continue
        if position == STEP:
            errors.append(_consecutive_steps())
            continue
        errors.append(_structural_after_step())
    if state == "after_step":
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "An alternative branch must not end with a step; it needs a closing SEQTRANSITION",
            )
        )


def _check_step_body(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``M* S (T M* S)*``: parallel branches and SUBSEQSTEP bodies."""
    positions = _elements(items)
    if not positions:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "A parallel branch or sub-step must contain at least one SEQSTEP",
            )
        )
        return
    state = "start"
    for position in positions:
        if state == "start":
            if position == STEP:
                state = "after_step"
            elif position == STRUCTURAL:
                continue
            else:
                errors.append(
                    _error(
                        DiagnosticCode.SFC_PARALLEL_BRANCH_START,
                        "Each PARALLELSEQ branch must start with a SEQSTEP",
                    )
                )
            continue
        if state == "after_step":
            if position == TRANSITION:
                state = "between"
            elif position == STEP:
                errors.append(_consecutive_steps())
            else:
                errors.append(_structural_after_step())
            continue
        # between a transition and the step that must follow it
        if position == STRUCTURAL:
            continue
        if position == STEP:
            state = "after_step"
            continue
        errors.append(_step_expected(position))
    if state != "after_step":
        errors.append(
            _error(
                DiagnosticCode.SFC_PARALLEL_BRANCH_START,
                "Each PARALLELSEQ branch must end with a SEQSTEP",
            )
        )


def _check_open(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``open_body``: an open sequence may stop anywhere, but still alternates."""
    positions = _elements(items)
    if not positions:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "An open sequence body must not be empty",
            )
        )
        return
    state = "start"
    for position in positions:
        if state == "start":
            state = "after_step" if position == STEP else "boundary"
            continue
        if state == "after_step":
            if position == TRANSITION:
                state = "boundary"
            elif position == STEP:
                errors.append(_consecutive_steps())
            else:
                errors.append(_structural_after_step())
            continue
        if position == STRUCTURAL:
            continue
        if position == STEP:
            state = "after_step"
            continue
        errors.append(_step_expected(position))
