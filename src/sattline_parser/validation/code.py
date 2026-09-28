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

from sattline_parser.models.ast_model import (
    CodeComment,
    DataType,
    Equation,
    ModuleCode,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCFork,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
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
from sattline_parser.validation.symbols import Scope, resolve_var

# Boolean constants the SattLine language provides but that resolve through the
# grammar as plain name references rather than True/False literals.
_SFC_RUNTIME_CONSTANTS = frozenset({"on", "off"})


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
    all_known = _collect_module_jump_target_names(mc.sequences)
    sfc_names = all_known | {sequence.name.casefold() for sequence in sequences if sequence.name}
    _check_duplicate_sfc_names(mc.sequences, errors)
    for sequence in sequences:
        _check_consecutive_steps(sequence.code, errors)
        _check_fork_targets(sequence.code, all_known, errors)
        _check_sequence_structure(sequence.code, errors)
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
            and expr.name.casefold() not in _SFC_RUNTIME_CONSTANTS
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
        walk_expression(item.condition, scope, records, sfc_names, errors)
    elif isinstance(item, SFCTransitionSub):
        walk_sequence_body(item.body, scope, records, sfc_names, errors)
    elif isinstance(item, SFCAlternative | SFCParallel):
        for branch in item.branches:
            walk_sequence_body(branch, scope, records, sfc_names, errors)
    elif isinstance(item, SFCSubsequence):
        walk_sequence_body(item.body, scope, records, sfc_names, errors)


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


def _is_sfc_runtime_accessor(ref: VarRef, sfc_names: set[str]) -> bool:
    """Dotted refs rooted on an SFC element/sequence name are step runtime accessors."""
    root = ref.name.partition(".")[0]
    return "." in ref.name and root.casefold() in sfc_names


def _check_consecutive_steps(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    last_was_step = False
    for item in items:
        if isinstance(item, CodeComment):
            continue
        is_step = isinstance(item, SFCStep)
        if last_was_step and is_step:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS,
                    message="Consecutive SFC steps without an intervening SEQTRANSITION",
                    span=None,
                )
            )
        last_was_step = is_step


def _collect_module_jump_target_names(sequences: list[Sequence] | None) -> set[str]:
    """Collect all step and transition names in a module code block for SEQFORK resolution."""
    names = _collect_jump_target_names([])
    for sequence in sequences or ():
        names |= _collect_jump_target_names(sequence.code)
    return names


def _collect_jump_target_names(items: list[SFCBodyItem]) -> set[str]:
    """Collect step and transition names a SEQFORK may jump to (intra-sequence)."""
    names: set[str] = set()
    for item in items:
        if isinstance(item, SFCStep | SFCTransition) and item.name is not None:
            names.add(item.name.casefold())
        elif isinstance(item, SFCTransitionSub):
            if item.name is not None:
                names.add(item.name.casefold())
            names.update(_collect_jump_target_names(item.body))
        elif isinstance(item, SFCAlternative | SFCParallel):
            for branch in item.branches:
                names.update(_collect_jump_target_names(branch))
        elif isinstance(item, SFCSubsequence):
            names.update(_collect_jump_target_names(item.body))
    return names


def _check_fork_targets(items: list[SFCBodyItem], known: set[str], errors: list[Diagnostic]) -> None:
    for item in items:
        if isinstance(item, SFCFork):
            for target in item.targets:
                if target.casefold() not in known:
                    errors.append(
                        Diagnostic(
                            code=DiagnosticCode.SEQUENCE_FORK_UNKNOWN_TARGET,
                            message=f"SEQFORK targets unknown step {target!r} in sequence",
                            span=None,
                        )
                    )
        elif isinstance(item, SFCAlternative | SFCParallel):
            for branch in item.branches:
                _check_fork_targets(branch, known, errors)
        elif isinstance(item, SFCSubsequence | SFCTransitionSub):
            _check_fork_targets(item.body, known, errors)


def _check_duplicate_sfc_names(sequences: list[Sequence] | None, errors: list[Diagnostic]) -> None:
    """Flag SFC element names that are reused within a module code block."""
    seen: set[str] = set()
    for sequence in sequences or ():
        _record_module_names(sequence.code, seen, errors)


def _record_module_names(items: list[SFCBodyItem], seen: set[str], errors: list[Diagnostic]) -> None:
    for item in items:
        name = _named_sfc_element_name(item)
        if name is not None:
            folded = name.casefold()
            if folded in seen:
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.DUPLICATE_SFC_ELEMENT_NAME,
                        message=f"SFC element name {name!r} is used by more than one step or transition",
                        span=None,
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


def _check_sequence_structure(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    """Enforce SEQINITSTEP placement and alternative/parallel branch layouts."""
    init_seen = False
    seen_non_init_element = False
    for item in items:
        if isinstance(item, CodeComment):
            continue
        if isinstance(item, SFCStep) and item.kind == "init":
            if init_seen:
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.SFC_INIT_STEP_PLACEMENT,
                        message="A sequence may contain only one SEQINITSTEP",
                        span=None,
                    )
                )
            elif seen_non_init_element:
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.SFC_INIT_STEP_PLACEMENT,
                        message="SEQINITSTEP must be the first element of a sequence",
                        span=None,
                    )
                )
            init_seen = True
        else:
            seen_non_init_element = True
        if isinstance(item, SFCAlternative):
            for branch in item.branches:
                _check_alternative_branch_start(branch, errors)
                _check_sequence_structure(branch, errors)
        elif isinstance(item, SFCParallel):
            for branch in item.branches:
                _check_parallel_branch_start(branch, errors)
                _check_sequence_structure(branch, errors)
        elif isinstance(item, SFCSubsequence | SFCTransitionSub):
            _check_sequence_structure(item.body, errors)


def _check_alternative_branch_start(branch: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    for item in branch:
        if isinstance(item, CodeComment):
            continue
        if not isinstance(item, SFCTransition | SFCTransitionSub | SFCAlternative | SFCParallel | SFCSubsequence):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.SFC_ALTERNATIVE_BRANCH_START,
                    message="Each ALTERNATIVESEQ branch must start with a SEQTRANSITION or a nested structure",
                    span=None,
                )
            )
        return


def _check_parallel_branch_start(branch: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    for item in branch:
        if isinstance(item, CodeComment):
            continue
        if not isinstance(item, SFCStep):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.SFC_PARALLEL_BRANCH_START,
                    message="Each PARALLELSEQ branch must start with a SEQSTEP",
                    span=None,
                )
            )
        return
