"""Module-code and SFC validation rules for a parsed BasePicture.

Walks equations/sequences/SFC bodies with a scope chain and flags intra-file
findings: :Old/:New on non-State symbols, writes to Const variables (direct
targets and built-in output arguments), references to undefined variables,
built-in call arity/direction errors, string-literal call arguments, sequence
structure (consecutive steps, init-step placement, unknown SEQFORK targets),
SFC structural layout (alternative/parallel branch starts), and duplicate SFC
element names.
"""

from __future__ import annotations

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    DataType,
    Equation,
    ModuleCode,
    ModuleDef,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCFork,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
    Simple_DataType,
    SourceSpan,
    Variable,
)
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    SLExpression,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.validation.builtins import builtin_function_signature
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.names import fold_identifier
from sattline_parser.validation.sequences import check_sequence_positions
from sattline_parser.validation.symbols import (
    Scope,
    is_sfc_runtime_constant,
    resolve_var,
)
from sattline_parser.validation.typing import (
    TypeFamily,
    assignment_is_compatible,
    assignment_types,
    datatype_family,
    infer_expr_type,
    is_boolean,
    is_numeric,
)

# Boolean constants the SattLine language provides but that resolve through the
# grammar as plain name references rather than True/False literals.


def walk_equation_block(
    equation: Equation,
    scope: Scope,
    records: dict[str, DataType],
    sfc_names: set[str],
    errors: list[Diagnostic],
) -> None:
    for item in equation.code:
        walk_code_item(item, scope, records, sfc_names, errors)


def walk_sequence_body(
    items: list[SFCBodyItem],
    scope: Scope,
    records: dict[str, DataType],
    sfc_names: set[str],
    errors: list[Diagnostic],
) -> None:
    for item in items:
        walk_sfc_item(item, scope, records, sfc_names, errors)


def walk_module_code(mc: ModuleCode, scope: Scope, records: dict[str, DataType], errors: list[Diagnostic]) -> None:
    sequences = mc.sequences or ()
    step_names, transition_names = _collect_module_jump_targets(mc.sequences)
    all_known = step_names | transition_names
    sfc_names = all_known | {fold_identifier(sequence.name) for sequence in sequences if sequence.name}
    _check_duplicate_sfc_names(mc.sequences, errors)
    check_sequence_positions(mc.sequences, errors)
    for sequence in sequences:
        _check_fork_targets(sequence.code, step_names, transition_names, errors)
        walk_sequence_body(sequence.code, scope, records, sfc_names, errors)
    for equation in mc.equations or ():
        walk_equation_block(equation, scope, records, sfc_names, errors)


def walk_code_item(
    item: object, scope: Scope, records: dict[str, DataType], sfc_names: set[str], errors: list[Diagnostic]
) -> None:
    if isinstance(item, Assignment):
        _check_assignment(item, scope, records, errors)
        walk_expression(item.value, scope, records, sfc_names, errors)
    elif isinstance(item, FuncCallStmt):
        _check_call(item.call, scope, records, sfc_names, errors)
        for arg in item.call.args:
            walk_expression(arg, scope, records, sfc_names, errors)
    elif isinstance(item, IfStmt):
        for condition, body in item.branches:
            _check_condition(condition, scope, records, errors)
            walk_expression(condition, scope, records, sfc_names, errors)
            for nested in body:
                walk_code_item(nested, scope, records, sfc_names, errors)
        for nested in item.else_block or ():
            walk_code_item(nested, scope, records, sfc_names, errors)


def walk_expression(
    expr: SLExpression, scope: Scope, records: dict[str, DataType], sfc_names: set[str], errors: list[Diagnostic]
) -> None:
    if isinstance(expr, VarRef):
        resolved = resolve_var(expr, scope, records)
        _check_old_new(expr, resolved, errors)
        if (
            resolved is None
            and not is_sfc_runtime_constant(expr.name)
            and not _is_sfc_runtime_accessor(expr, sfc_names)
        ):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.UNDEFINED_VARIABLE,
                    message=f"Reference to undefined variable {expr.name!r}",
                    span=expr.span,
                )
            )
    elif isinstance(expr, BoolOp):
        for operand in expr.operands:
            walk_expression(operand, scope, records, sfc_names, errors)
    elif isinstance(expr, NotOp):
        walk_expression(expr.operand, scope, records, sfc_names, errors)
    elif isinstance(expr, Compare | BinOp):
        _check_operands(expr, scope, records, errors)
        walk_expression(expr.left, scope, records, sfc_names, errors)
        walk_expression(expr.right, scope, records, sfc_names, errors)
    elif isinstance(expr, UnaryOp):
        walk_expression(expr.operand, scope, records, sfc_names, errors)
    elif isinstance(expr, FuncCall):
        _check_call(expr, scope, records, sfc_names, errors)
        for arg in expr.args:
            walk_expression(arg, scope, records, sfc_names, errors)
    elif isinstance(expr, TernaryOp):
        for condition, then_expr in expr.branches:
            _check_condition(condition, scope, records, errors)
            walk_expression(condition, scope, records, sfc_names, errors)
            walk_expression(then_expr, scope, records, sfc_names, errors)
        if expr.else_expr is not None:
            walk_expression(expr.else_expr, scope, records, sfc_names, errors)


def walk_sfc_item(
    item: SFCBodyItem, scope: Scope, records: dict[str, DataType], sfc_names: set[str], errors: list[Diagnostic]
) -> None:
    if isinstance(item, SFCStep):
        for block in (item.code.enter, item.code.active, item.code.exit):
            for code_item in block:
                walk_code_item(code_item, scope, records, sfc_names, errors)
    elif isinstance(item, SFCTransition):
        if item.condition is not None:
            walk_expression(item.condition, scope, records, sfc_names, errors)
    elif isinstance(item, SFCTransitionSub):
        walk_sequence_body(item.body, scope, records, sfc_names, errors)
    elif isinstance(item, SFCAlternative | SFCParallel):
        for branch in item.branches:
            walk_sequence_body(branch, scope, records, sfc_names, errors)
    elif isinstance(item, SFCSubsequence):
        walk_sequence_body(item.body, scope, records, sfc_names, errors)


def _check_operands(
    expr: Compare | BinOp, scope: Scope, records: dict[str, DataType], errors: list[Diagnostic]
) -> None:
    """Operands of an operator must be of a type the operator accepts.

    The diagnostic reads ``Only integer and real allowed for this operator
    <expr>``.

    A comparison also tolerates one temporal operand against a numeric one:
    ``Elapsed == 5``, ``Elapsed > 2.5`` and ``Stamp == 5`` are accepted, while
    two temporal operands such as ``ZeroDur == ZeroFull`` are rejected with the
    same message. The rule is therefore "a numeric operand may be compared with
    a temporal one", not "temporal operands are allowed".

    Arithmetic keeps the strict numeric-only rule: the message is an arithmetic
    one and no temporal operand is accepted there.
    """
    operand_types = [infer_expr_type(operand, scope, records) for operand in (expr.left, expr.right)]
    for position, operand_type in enumerate(operand_types):
        if operand_type is None or is_numeric(operand_type):
            continue
        if datatype_family(operand_type) is TypeFamily.TEMPORAL:
            other = operand_types[1 - position]
            if isinstance(expr, Compare) and other is not None and is_numeric(other):
                continue
        errors.append(
            Diagnostic(
                code=DiagnosticCode.OPERAND_NOT_NUMERIC,
                message=(
                    f"Only integer and real allowed for this operator {expr.op}; operand is of type {operand_type}"
                ),
                span=_expression_span(expr),
            )
        )


def _check_condition(
    condition: SLExpression, scope: Scope, records: dict[str, DataType], errors: list[Diagnostic]
) -> None:
    """An IF / ELSIF / ternary condition must be boolean.

    Real message: ``Condition in IF-sentence is not boolean``.
    """
    condition_type = infer_expr_type(condition, scope, records)
    if condition_type is not None and not is_boolean(condition_type):
        errors.append(
            Diagnostic(
                code=DiagnosticCode.CONDITION_NOT_BOOLEAN,
                message=f"Condition in IF-sentence is not boolean; condition is of type {condition_type}",
                span=_expression_span(condition),
            )
        )


def _expression_span(expr: SLExpression) -> SourceSpan | None:
    """Span of a parsed expression node; primitives carry none."""
    span = getattr(expr, "span", None)
    return span if isinstance(span, SourceSpan) else None


def check_coordinate_tail_types(
    module_def: ModuleDef, scope: Scope, records: dict[str, DataType], errors: list[Diagnostic]
) -> None:
    """A coordinate position must be real, never integer (SL-V032).

    The diagnostic reads *"The expression is of an invalid type Source + 1"*
    for an integer-typed ``ClippingBounds`` corner tail, and the error disappears
    once the same tail is declared ``real``. The constraint is on the coordinate
    *position*, so it applies to every collected tail, not just computed ones:
    a bare integer variable in a corner is rejected the same way.

    ``str`` tails are skipped. An ``InVar_ "Name"`` tail carries a variable
    *reference*, not a value, and resolving the name is not evidenced.
    Unknown types stay silent, as elsewhere in this module.
    """
    seen: set[int] = set()
    tails: list[object] = [*(module_def.clipping_tails or []), *(module_def.properties.get(const.KEY_TAILS) or [])]
    for tail in tails:
        if not isinstance(tail, BoolOp | NotOp | Compare | BinOp | UnaryOp | FuncCall | TernaryOp | VarRef):
            continue
        if id(tail) in seen:
            continue
        seen.add(id(tail))
        inferred = infer_expr_type(tail, scope, records)
        if inferred is not None and fold_identifier(inferred) != fold_identifier(Simple_DataType.REAL.value):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.COORDINATE_NOT_REAL,
                    message=(
                        f"Coordinate position is of an invalid type: it is {inferred}, but a coordinate must be a real"
                    ),
                    span=_expression_span(tail),
                )
            )


def _check_assignment(
    assignment: Assignment, scope: Scope, records: dict[str, DataType], errors: list[Diagnostic]
) -> None:
    resolved = resolve_var(assignment.target, scope, records)
    if resolved is None:
        errors.append(
            Diagnostic(
                code=DiagnosticCode.UNDEFINED_VARIABLE,
                message=f"Assignment to undefined variable {assignment.target.name!r}",
                span=assignment.span,
            )
        )
        return
    if resolved.const:
        errors.append(
            Diagnostic(
                code=DiagnosticCode.WRITE_TO_CONST_VARIABLE,
                message=f"Cannot assign to Const variable {assignment.target.name} in module code",
                span=assignment.span,
            )
        )
    _check_old_new(assignment.target, resolved, errors)
    _check_old_write_target(assignment.target, resolved, errors)
    target_type, source_type = assignment_types(assignment, scope, records)
    if target_type is not None and source_type is not None and not assignment_is_compatible(source_type, target_type):
        errors.append(
            Diagnostic(
                code=DiagnosticCode.ASSIGNMENT_TYPE_MISMATCH,
                message=(
                    f"Datatype error in assignment: {assignment.target.name} is of type {target_type} "
                    f"but is assigned a value of type {source_type}"
                ),
                span=assignment.span,
            )
        )


def _check_old_write_target(ref: VarRef, resolved: Variable | None, errors: list[Diagnostic]) -> None:
    """``:Old`` is a read state; the compiler rejects it as a write target.

    Statement analysis rejects an ``:Old`` assignment target with
    expression-node error 0x14, and reference-required call arguments follow the
    same rule. This is a *semantic* rejection, distinct from the syntax that
    still has to parse ``:Old`` (STATE-01/STATE-02).
    """
    if ref.state != "old" or resolved is None or not resolved.state:
        return
    errors.append(
        Diagnostic(
            code=DiagnosticCode.OLD_STATE_NOT_WRITABLE,
            message=f"Cannot write to {ref.name}:Old; the Old state of a State variable is read-only",
            span=ref.span,
        )
    )


def _check_old_new(ref: VarRef, resolved: Variable | None, errors: list[Diagnostic]) -> None:
    if ref.state not in ("old", "new"):
        return
    if resolved is None or resolved.state:
        return
    is_field = "." in ref.name
    code = DiagnosticCode.OLD_NEW_ON_NON_STATE_FIELD if is_field else DiagnosticCode.OLD_NEW_ON_NON_STATE_VARIABLE
    kind = "field" if is_field else "variable"
    errors.append(
        Diagnostic(
            code=code,
            message=f":{ref.state} is only valid on State {kind}s; '{ref.name}' is not declared State",
            span=ref.span,
        )
    )


def _check_call(
    call: FuncCall, scope: Scope, records: dict[str, DataType], sfc_names: set[str], errors: list[Diagnostic]
) -> None:
    for arg in call.args:
        if isinstance(arg, str):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.STRING_LITERAL_CALL_ARGUMENT,
                    message=f"String literal argument {arg!r} is not allowed in call to {call.name}",
                    span=call.span,
                )
            )
    signature = builtin_function_signature(call.name)
    if signature is None:
        return
    if not signature.min_args <= len(call.args) <= signature.max_args:
        errors.append(
            Diagnostic(
                code=DiagnosticCode.BUILTIN_WRONG_ARITY,
                message=(
                    f"Built-in {signature.name} expects {signature.min_args}"
                    f"{'' if signature.min_args == signature.max_args else '..' + str(signature.max_args)} "
                    f"arguments but was given {len(call.args)}"
                ),
                span=call.span,
            )
        )
    for position in signature.out_arg_positions:
        index = position - 1
        if index >= len(call.args):
            continue
        arg = call.args[index]
        if not isinstance(arg, VarRef):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.BUILTIN_OUT_ARG_NOT_VARIABLE,
                    message=(
                        f"Argument {position} of built-in {signature.name} is an output and must be a "
                        "plain variable reference"
                    ),
                    span=call.span,
                )
            )
            continue
        resolved = resolve_var(arg, scope, records)
        if resolved is not None and resolved.const:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.WRITE_TO_CONST_VARIABLE,
                    message=(
                        f"Cannot use Const variable {arg.name!r} as output argument {position} "
                        f"of built-in {signature.name}"
                    ),
                    span=call.span,
                )
            )
        _check_old_write_target(arg, resolved, errors)


def _is_sfc_runtime_accessor(ref: VarRef, sfc_names: set[str]) -> bool:
    """Dotted refs rooted on an SFC element/sequence name are step runtime accessors."""
    root = ref.name.partition(".")[0]
    return "." in ref.name and fold_identifier(root) in sfc_names


def _collect_module_jump_targets(sequences: list[Sequence] | None) -> tuple[set[str], set[str]]:
    """Collect step and transition names across the module's sequences.

    Fork names resolve during analysis against the module's sequence-name
    registry; a narrower "current sequence only" scope could not be
    established, so every sequence in the module code block contributes here.
    """
    step_names: set[str] = set()
    transition_names: set[str] = set()
    for sequence in sequences or ():
        _collect_jump_targets(sequence.code, step_names, transition_names)
    return step_names, transition_names


def _collect_jump_targets(items: list[SFCBodyItem], step_names: set[str], transition_names: set[str]) -> None:
    for item in items:
        if isinstance(item, SFCStep):
            if item.name is not None:
                step_names.add(fold_identifier(item.name))
        elif isinstance(item, SFCTransition | SFCTransitionSub):
            if item.name is not None:
                transition_names.add(fold_identifier(item.name))
            if isinstance(item, SFCTransitionSub):
                _collect_jump_targets(item.body, step_names, transition_names)
        elif isinstance(item, SFCAlternative | SFCParallel):
            for branch in item.branches:
                _collect_jump_targets(branch, step_names, transition_names)
        elif isinstance(item, SFCSubsequence):
            if item.kind == "substep" and item.name is not None:
                step_names.add(fold_identifier(item.name))
            _collect_jump_targets(item.body, step_names, transition_names)


def _check_fork_targets(
    items: list[SFCBodyItem], step_names: set[str], transition_names: set[str], errors: list[Diagnostic]
) -> None:
    """Resolve every SEQFORK target and check its kind.

    Unresolved or wrong-kind targets are rejected. A fork hosted on a step must
    name transitions, and a fork hosted on a transition must name steps; a rule
    that merely required every target to be a step would be wrong.
    """

    def _check_fork(fork: SFCFork | None, host: str, span: SourceSpan | None) -> None:
        if fork is None:
            return
        expected = transition_names if host == "step" else step_names
        other = step_names if host == "step" else transition_names
        expected_kind = "transition" if host == "step" else "step"
        for target in fork.targets:
            folded = fold_identifier(target)
            if folded in expected:
                continue
            if folded in other:
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.SEQUENCE_FORK_TARGET_KIND,
                        message=(
                            f"SEQFORK on a {host} must target a {expected_kind}; {target!r} is a "
                            f"{'step' if expected_kind == 'transition' else 'transition'}"
                        ),
                        span=span,
                    )
                )
                continue
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.SEQUENCE_FORK_UNKNOWN_TARGET,
                    message=f"SEQFORK targets unknown SFC element {target!r} in module",
                    span=span,
                )
            )

    for item in items:
        if isinstance(item, SFCStep):
            _check_fork(item.fork, "step", item.span)
        elif isinstance(item, SFCTransition):
            _check_fork(item.fork, "transition", item.span)
        elif isinstance(item, SFCAlternative | SFCParallel):
            for branch in item.branches:
                _check_fork_targets(branch, step_names, transition_names, errors)
        elif isinstance(item, SFCSubsequence | SFCTransitionSub):
            _check_fork_targets(item.body, step_names, transition_names, errors)


def _check_duplicate_sfc_names(sequences: list[Sequence] | None, errors: list[Diagnostic]) -> None:
    """Flag SFC element names that are reused within a module code block."""
    seen: set[str] = set()
    for sequence in sequences or ():
        _record_module_names(sequence.code, seen, errors)


def _record_module_names(items: list[SFCBodyItem], seen: set[str], errors: list[Diagnostic]) -> None:
    for item in items:
        name = _named_sfc_element_name(item)
        if name is not None:
            folded = fold_identifier(name)
            if folded in seen:
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.DUPLICATE_SFC_ELEMENT_NAME,
                        message=f"SFC element name {name!r} is used by more than one step or transition",
                        span=item.span,
                    )
                )
            else:
                seen.add(folded)
        if isinstance(item, SFCAlternative | SFCParallel):
            for branch in item.branches:
                _record_module_names(branch, seen, errors)
        elif isinstance(item, SFCSubsequence | SFCTransitionSub):
            _record_module_names(item.body, seen, errors)


def _named_sfc_element_name(item: SFCBodyItem) -> str | None:
    if isinstance(item, SFCSubsequence):
        return item.name
    if isinstance(item, SFCStep | SFCTransition | SFCTransitionSub):
        return item.name
    return None
