"""Sequence element-position validation (S/T/M productions).

Each sequence construct classifies into exactly one position, and only specific
interleavings are accepted. The three starter sets define the positions:

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
and therefore never appears here.
"""

from __future__ import annotations

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    CodeComment,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCLoop,
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
    if isinstance(item, SFCLoop):
        # A loop carries its own closed body and takes the structural (M) slot
        # (``FreeWord1`` sits in M_FIRST alongside SUBSEQUENCE).
        return STRUCTURAL
    # The union is exhausted down to SFCSubsequence here; a sub-step occupies the
    # step position and a plain sub-sequence the structural one.
    return STEP if item.kind == "substep" else STRUCTURAL


#: A positioned sequence element: its S/T/M position and the node itself, so a
#: diagnostic can point at the exact element instead of only describing it.
type PositionedElement = tuple[str, SFCBodyItem]


def _elements(items: list[SFCBodyItem]) -> list[PositionedElement]:
    elements: list[PositionedElement] = []
    for item in items:
        position = _position(item)
        if position is not None:
            elements.append((position, item))
    return elements


def _error(code: DiagnosticCode, message: str, item: SFCBodyItem | None = None) -> Diagnostic:
    return Diagnostic(code=code, message=message, span=item.span if item is not None else None)


def _consecutive_steps(item: SFCBodyItem) -> Diagnostic:
    return _error(
        DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS,
        "Consecutive SFC steps without an intervening SEQTRANSITION",
        item,
    )


def _structural_after_step(item: SFCBodyItem) -> Diagnostic:
    return _error(
        DiagnosticCode.SEQUENCE_POSITION_INVALID,
        "A structural element (SUBSEQUENCE or loop) cannot appear between a SEQSTEP and its SEQTRANSITION",
        item,
    )


def _step_before_transition(position: str, item: SFCBodyItem) -> Diagnostic:
    detail = "a structural construct" if position == STRUCTURAL else "another transition"
    return _error(
        DiagnosticCode.SEQUENCE_POSITION_INVALID,
        f"Expected a SEQSTEP before this element, found {detail}; steps and transitions must alternate",
        item,
    )


def _step_expected(position: str, item: SFCBodyItem) -> Diagnostic:
    detail = "a transition" if position == TRANSITION else "a structural construct"
    return _error(
        DiagnosticCode.SEQUENCE_POSITION_INVALID,
        f"Expected a SEQSTEP before this element, found {detail}",
        item,
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
        elif isinstance(item, SFCLoop):
            _check_body(item.body, CLOSED, errors)
            if item.else_body is not None:
                _check_body(item.else_body, CLOSED, errors)


def _check_closed(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``(S T | M)+``: units alternate and the body ends after a T or an M."""
    elements = _elements(items)
    if not elements:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "A sequence body must contain at least one step/transition pair or structural construct",
            )
        )
        return
    expecting_unit = True
    for position, item in elements:
        if expecting_unit:
            if position == STEP:
                expecting_unit = False
            elif position == TRANSITION:
                errors.append(_step_before_transition(position, item))
            continue
        if position == TRANSITION:
            expecting_unit = True
            continue
        if position == STEP:
            errors.append(_consecutive_steps(item))
            continue
        errors.append(_structural_after_step(item))
    if not expecting_unit:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_ENDS_WITH_STEP,
                "A sequence must not end with a step; it must end with a SEQTRANSITION before ENDSEQUENCE",
                elements[-1][1],
            )
        )


def _check_transition_body(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``T (S T | M)*``: alternative branches and SUBSEQTRANSITION bodies."""
    elements = _elements(items)
    if not elements:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "An alternative branch or sub-transition must contain at least one SEQTRANSITION",
            )
        )
        return
    first, first_item = elements[0]
    if first != TRANSITION:
        errors.append(
            _error(
                DiagnosticCode.SFC_ALTERNATIVE_BRANCH_START,
                "Each ALTERNATIVESEQ branch must start with a SEQTRANSITION or a nested structure",
                first_item,
            )
        )
    state = "unit" if first == TRANSITION else ("after_step" if first == STEP else "unit")
    for position, item in elements[1:]:
        if state == "unit":
            if position == STEP:
                state = "after_step"
            elif position == TRANSITION:
                errors.append(_step_before_transition(position, item))
            continue
        if position == TRANSITION:
            state = "unit"
            continue
        if position == STEP:
            errors.append(_consecutive_steps(item))
            continue
        errors.append(_structural_after_step(item))
    if state == "after_step":
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "An alternative branch must not end with a step; it needs a closing SEQTRANSITION",
                elements[-1][1],
            )
        )


def _check_step_body(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``M* S (T M* S)*``: parallel branches and SUBSEQSTEP bodies."""
    elements = _elements(items)
    if not elements:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "A parallel branch or sub-step must contain at least one SEQSTEP",
            )
        )
        return
    state = "start"
    for position, item in elements:
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
                        item,
                    )
                )
            continue
        if state == "after_step":
            if position == TRANSITION:
                state = "between"
            elif position == STEP:
                errors.append(_consecutive_steps(item))
            else:
                errors.append(_structural_after_step(item))
            continue
        # between a transition and the step that must follow it
        if position == STRUCTURAL:
            continue
        if position == STEP:
            state = "after_step"
            continue
        errors.append(_step_expected(position, item))
    if state != "after_step":
        errors.append(
            _error(
                DiagnosticCode.SFC_PARALLEL_BRANCH_START,
                "Each PARALLELSEQ branch must end with a SEQSTEP",
                elements[-1][1],
            )
        )


def _check_open(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """``open_body``: an open sequence may stop anywhere, but still alternates."""
    elements = _elements(items)
    if not elements:
        errors.append(
            _error(
                DiagnosticCode.SEQUENCE_POSITION_INVALID,
                "An open sequence body must not be empty",
            )
        )
        return
    state = "start"
    for position, item in elements:
        if state == "start":
            state = "after_step" if position == STEP else "boundary"
            continue
        if state == "after_step":
            if position == TRANSITION:
                state = "boundary"
            elif position == STEP:
                errors.append(_consecutive_steps(item))
            else:
                errors.append(_structural_after_step(item))
            continue
        if position == STRUCTURAL:
            continue
        if position == STEP:
            state = "after_step"
            continue
        errors.append(_step_expected(position, item))
