"""Module-code and SFC validation rules for a parsed BasePicture.

Walks equation blocks, sequences, and SFC bodies with a scope chain and flags intra-file
findings: :Old/:New on non-State symbols, writes to Const variables (direct
targets and built-in output arguments), references to undefined variables,
built-in call arity/direction errors, string-literal call arguments, sequence
structure (consecutive steps, init-step placement, unknown SEQFORK targets),
SFC structural layout (alternative/parallel branch starts), and duplicate step
and transition names.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sattline_parser.models import walk
from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    Equation,
    FrameModule,
    ModuleCode,
    ModuleTypeInstance,
    ScalarDatatype,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCFork,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
    SingleModule,
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
from sattline_parser.names import fold_identifier
from sattline_parser.validation.builtins import BuiltinFunction, builtin_function_signature
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.sequences import check_sequence_positions
from sattline_parser.validation.symbols import (
    Scope,
    is_const_reference,
    resolve_var,
)
from sattline_parser.validation.type_graph import TypeGraph
from sattline_parser.validation.typing import (
    TypeFamily,
    assignment_type_matches,
    assignment_types,
    builtin_type_matches,
    datatype_family,
    infer_expr_type,
    is_anytype_datatype,
    is_boolean,
    is_numeric,
    is_string_simple_type,
    merge_compatible_types,
    unresolved_reference_is_a_defect,
)

_EQUALITY_COMPARISON_OPERATORS = frozenset({"==", "=", "!=", "<>"})

#: The runtime fields an SFC element may expose. A root reached only through
#: ``program_sfc_names`` has no sequence context, so this is the fallback set;
#: a root declared in the current module uses its element-kind set instead.
_SFC_STEP_ACCESSOR_SUFFIXES = frozenset({"x", "hold", "reset", "t"})
_SFC_SEQUENCE_ACCESSOR_SUFFIXES = frozenset({"hold", "reset"})
_SFC_ACCESSOR_SUFFIXES = _SFC_STEP_ACCESSOR_SUFFIXES


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """State shared by every step of one module-code validation walk."""

    scope: Scope
    records: dict[str, DataType]
    type_graph: TypeGraph
    sfc_names: set[str]
    errors: list[Diagnostic]
    sfc_accessors: dict[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])


def walk_equation_block(equation: Equation, context: ValidationContext) -> None:
    for item in equation.code:
        walk_code_item(item, context)


def walk_sequence_body(items: list[SFCBodyItem], context: ValidationContext) -> None:
    for item in items:
        walk_sfc_item(item, context)


def _iter_program_module_codes(bp: BasePicture) -> list[ModuleCode]:
    """Every ``ModuleCode`` block in one program file, nested modules included."""
    codes: list[ModuleCode] = []
    if bp.modulecode is not None:
        codes.append(bp.modulecode)
    pending: list[SingleModule | FrameModule | ModuleTypeInstance] = list(bp.submodules)
    for moduletype in bp.moduletype_defs:
        if moduletype.modulecode is not None:
            codes.append(moduletype.modulecode)
        pending.extend(moduletype.submodules)
    while pending:
        child = pending.pop()
        if isinstance(child, ModuleTypeInstance):
            continue
        if child.modulecode is not None:
            codes.append(child.modulecode)
        pending.extend(child.submodules)
    return codes


def collect_program_sfc_names(bp: BasePicture) -> frozenset[str]:
    """Every SFC step and sequence name visible anywhere in one program file.

    SFC element names resolve program-wide: an equation block refers to a
    sequence defined in a *nested* frame module by name (``Seq.Reset``), so a
    module-local set alone would report those references as undefined.
    """
    names: set[str] = set()
    for code in _iter_program_module_codes(bp):
        steps, _transitions = _collect_module_jump_targets(code.sequences)
        names |= steps
        names |= {fold_identifier(sequence.name) for sequence in code.sequences or () if sequence.name}
    return frozenset(names)


def walk_module_code(
    mc: ModuleCode,
    context: ValidationContext,
    *,
    program_sfc_names: frozenset[str] = frozenset(),
) -> None:
    sequences = list(mc.sequences or ())
    step_names, transition_names = _collect_module_jump_targets(mc.sequences)
    name_counts = _collect_module_sfc_name_counts(mc.sequences)
    all_known = step_names | transition_names
    sfc_names = (
        all_known | {fold_identifier(sequence.name) for sequence in sequences if sequence.name} | program_sfc_names
    )
    _steps, step_features, _sequence_names, sequence_features = _collect_sequence_features(sequences)
    # The shape map lists the fields an element can expose, not the fields it
    # currently enables. ``check_step_auto_variables`` reports a missing
    # SeqControl/SeqTimer, so an unavailable-but-known field stays an accessor
    # here and does not also become an undefined reference.
    accessors: dict[str, frozenset[str]] = dict.fromkeys(step_features, _SFC_STEP_ACCESSOR_SUFFIXES)
    for key in sequence_features:
        accessors[key] = accessors.get(key, frozenset()) | _SFC_SEQUENCE_ACCESSOR_SUFFIXES
    module_context = replace(context, sfc_names=set(sfc_names), sfc_accessors=accessors)
    _check_duplicate_sfc_names(mc.sequences, context.errors)
    check_sequence_positions(mc.sequences, context.errors)
    check_step_auto_variables(mc, context)
    for sequence in sequences:
        _check_fork_targets(sequence.code, step_names, transition_names, name_counts, context.errors)
        walk_sequence_body(sequence.code, module_context)
    for equation in mc.equationblocks or ():
        walk_equation_block(equation, module_context)


def _iter_var_refs(node: object) -> list[VarRef]:
    """Every ``VarRef`` under ``node``, in source order."""
    return [event.node for event in walk(node) if isinstance(event.node, VarRef)]


def _iter_sfc_var_refs(items: list[SFCBodyItem]) -> list[VarRef]:
    """Every ``VarRef`` in an SFC body, in source order."""
    return [event.node for event in walk(items) if isinstance(event.node, VarRef)]


def _collect_sequence_features(
    sequences: list[Sequence],
) -> tuple[dict[str, str], dict[str, set[str]], dict[str, str], dict[str, set[str]]]:
    steps: dict[str, str] = {}
    step_features: dict[str, set[str]] = {}
    sequences_by_key: dict[str, str] = {}
    sequence_features: dict[str, set[str]] = {}
    for sequence in sequences:
        sequence_key = fold_identifier(sequence.name or "")
        sequences_by_key.setdefault(sequence_key, sequence.name or "")
        features = sequence_features.setdefault(sequence_key, set())
        if sequence.seqcontrol:
            features.update({"hold", "reset"})
        _collect_step_features(sequence.code, bool(sequence.seqcontrol), bool(sequence.seqtimer), steps, step_features)
    return steps, step_features, sequences_by_key, sequence_features


def _collect_step_features(
    items: list[SFCBodyItem],
    seqcontrol: bool,
    seqtimer: bool,
    steps: dict[str, str],
    step_features: dict[str, set[str]],
) -> None:
    for item in items:
        if isinstance(item, SFCStep):
            key = fold_identifier(item.name or "")
            steps.setdefault(key, item.name or "")
            features = step_features.setdefault(key, set())
            features.add("x")
            if seqcontrol:
                features.update({"hold", "reset"})
            if seqtimer:
                features.add("t")
        elif isinstance(item, (SFCAlternative, SFCParallel)):
            for branch in item.branches:
                _collect_step_features(branch, seqcontrol, seqtimer, steps, step_features)
        elif isinstance(item, (SFCSubsequence, SFCTransitionSub)):
            _collect_step_features(item.body, seqcontrol, seqtimer, steps, step_features)


def check_step_auto_variables(mc: ModuleCode, context: ValidationContext) -> None:
    """Check step/sequence runtime accessors such as ``Step.X`` and ``Step.Hold``.

    A step always exposes ``.X``; ``.Hold``/``.Reset`` require ``SeqControl`` on
    the enclosing sequence and ``.T`` requires ``SeqTimer``. A sequence exposes
    ``.Hold``/``.Reset`` under the same condition. Unknown roots and unknown
    suffixes stay with the undefined-variable rule, so this only reports known
    elements that lack the requested feature.
    """
    sequences = mc.sequences or ()
    if not sequences:
        return
    steps, step_features, sequences_by_key, sequence_features = _collect_sequence_features(sequences)
    refs: list[VarRef] = []
    for equation in mc.equationblocks or ():
        refs.extend(_iter_var_refs(equation.code))
    for sequence in sequences:
        refs.extend(_iter_sfc_var_refs(sequence.code))

    for ref in refs:
        base_name, field_path = ref.name.partition(".")[0], ref.name.partition(".")[2]
        if not base_name or not field_path or "." in field_path:
            continue
        suffix = field_path.casefold()
        if suffix not in {"x", "hold", "reset", "t"}:
            continue
        if context.scope.lookup(base_name) is not None:
            continue
        base_key = fold_identifier(base_name)
        step_name = steps.get(base_key)
        if step_name is None:
            sequence_name = sequences_by_key.get(base_key)
            if sequence_name is None or suffix not in {"hold", "reset"}:
                continue
            if suffix in sequence_features.get(base_key, set()):
                continue
            feature = "Hold" if suffix == "hold" else "Reset"
            context.errors.append(
                Diagnostic(
                    code=DiagnosticCode.STEP_AUTO_VARIABLE_UNAVAILABLE,
                    message=(
                        f"Variable reference {ref.name!r} is not available: "
                        f"sequence {sequence_name!r} only exposes .{feature} when it enables SeqControl"
                    ),
                    span=ref.span,
                )
            )
            continue
        features = step_features.get(base_key, set())
        if suffix == "x" or suffix in features:
            continue
        feature = {"hold": "Hold", "reset": "Reset", "t": "T"}[suffix]
        reason = "SeqTimer" if suffix == "t" else "SeqControl"
        context.errors.append(
            Diagnostic(
                code=DiagnosticCode.STEP_AUTO_VARIABLE_UNAVAILABLE,
                message=(
                    f"Variable reference {ref.name!r} is not available: "
                    f"step {step_name!r} only exposes .{feature} when its sequence enables {reason}"
                ),
                span=ref.span,
            )
        )


def walk_code_item(item: object, context: ValidationContext) -> None:
    if isinstance(item, Assignment):
        _check_assignment(item, context)
        walk_expression(item.value, context)
    elif isinstance(item, FuncCallStmt):
        _check_call(item.call, context)
        for arg in item.call.args:
            walk_expression(arg, context)
    elif isinstance(item, IfStmt):
        for condition, body in item.branches:
            _check_condition(condition, context)
            walk_expression(condition, context)
            for nested in body:
                walk_code_item(nested, context)
        for nested in item.else_block or ():
            walk_code_item(nested, context)


def walk_expression(expr: SLExpression, context: ValidationContext) -> None:
    if isinstance(expr, VarRef):
        resolved = resolve_var(expr, context.scope, context.records)
        check_old_new(expr, None if resolved is None else bool(resolved.state), context.errors)
        if (
            resolved is None
            and unresolved_reference_is_a_defect(expr, context.scope, context.type_graph)
            and not _is_sfc_runtime_accessor(expr, context.sfc_names, context.sfc_accessors)
        ):
            context.errors.append(
                Diagnostic(
                    code=DiagnosticCode.UNDEFINED_VARIABLE,
                    message=f"Reference to undefined variable {expr.name!r}",
                    span=expr.span,
                )
            )
    elif isinstance(expr, BoolOp):
        _check_bool_operand(expr, context)
        for operand in expr.operands:
            walk_expression(operand, context)
    elif isinstance(expr, NotOp):
        _check_bool_operand(expr, context)
        walk_expression(expr.operand, context)
    elif isinstance(expr, (Compare, BinOp)):
        _check_operands(expr, context)
        walk_expression(expr.left, context)
        walk_expression(expr.right, context)
    elif isinstance(expr, UnaryOp):
        _check_unary_operand(expr, context)
        walk_expression(expr.operand, context)
    elif isinstance(expr, FuncCall):
        _check_procedure_value_position(expr, context)
        _check_call(expr, context)
        for arg in expr.args:
            walk_expression(arg, context)
    elif isinstance(expr, TernaryOp):
        _check_ternary_branches(expr, context)
        for condition, then_expr in expr.branches:
            _check_condition(condition, context)
            walk_expression(condition, context)
            walk_expression(then_expr, context)
        if expr.else_expr is not None:
            walk_expression(expr.else_expr, context)


def walk_sfc_item(item: SFCBodyItem, context: ValidationContext) -> None:
    if isinstance(item, SFCStep):
        for block in (item.code.enter, item.code.active, item.code.exit):
            for code_item in block:
                walk_code_item(code_item, context)
    elif isinstance(item, SFCTransition):
        if item.condition is not None:
            _check_condition(item.condition, context, construct="transition guard")
            walk_expression(item.condition, context)
    elif isinstance(item, SFCTransitionSub):
        walk_sequence_body(item.body, context)
    elif isinstance(item, (SFCAlternative, SFCParallel)):
        for branch in item.branches:
            walk_sequence_body(branch, context)
    elif isinstance(item, SFCSubsequence):
        walk_sequence_body(item.body, context)


def _temporal_numeric_pair(left_type: str | None, right_type: str | None) -> bool:
    """A temporal operand may be compared with a numeric one (``Elapsed == 5``)."""
    if left_type is None or right_type is None:
        return False
    left_family = datatype_family(left_type)
    right_family = datatype_family(right_type)
    return (left_family is TypeFamily.TEMPORAL and is_numeric(right_type)) or (
        right_family is TypeFamily.TEMPORAL and is_numeric(left_type)
    )


def _check_operands(expr: Compare | BinOp, context: ValidationContext) -> None:
    """Operands of an operator must be of a type the operator accepts.

    A comparison splits by operator: equality accepts any two compatible
    types (two strings, two records of the same type, numeric pairs), while
    ordering requires numeric operands. Arithmetic requires numeric operands
    on both sides.

    Each offending operand gets its own finding, carrying that operand's span
    and name. Two operands of the same type are then distinguishable, and the
    finding points at the operand rather than at the whole expression.
    """
    left_operand, right_operand = expr.left, expr.right
    left_type = infer_expr_type(left_operand, context.scope, context.records, context.type_graph)
    right_type = infer_expr_type(right_operand, context.scope, context.records, context.type_graph)
    operands: tuple[tuple[SLExpression, str | None], ...] = (
        (left_operand, left_type),
        (right_operand, right_type),
    )

    if isinstance(expr, Compare):
        if expr.op in _EQUALITY_COMPARISON_OPERATORS:
            both_temporal = (
                left_type is not None
                and right_type is not None
                and datatype_family(left_type) is TypeFamily.TEMPORAL
                and datatype_family(right_type) is TypeFamily.TEMPORAL
            )
            incompatible = (
                left_type is not None
                and right_type is not None
                and not is_anytype_datatype(left_type)
                and not is_anytype_datatype(right_type)
                and merge_compatible_types((left_type, right_type)) is None
                and not _temporal_numeric_pair(left_type, right_type)
            )
            if both_temporal:
                for operand, operand_type in operands:
                    context.errors.append(
                        Diagnostic(
                            code=DiagnosticCode.OPERAND_NOT_NUMERIC,
                            message=(
                                f"Only integer and real allowed for this operator {expr.op}; "
                                f"{_describe_operand(operand)} is of type {operand_type}"
                            ),
                            span=_operand_span(expr, operand),
                        )
                    )
            elif incompatible:
                context.errors.append(
                    Diagnostic(
                        code=DiagnosticCode.COMPARE_INCOMPATIBLE_OPERANDS,
                        message=(
                            f"Comparison operator {expr.op!r} expects compatible operands but got "
                            f"{left_type!r} and {right_type!r}"
                        ),
                        span=_expression_span(expr),
                    )
                )
            return

        for position, (operand, operand_type) in enumerate(operands):
            if operand_type is None or is_anytype_datatype(operand_type) or is_numeric(operand_type):
                continue
            other_type = operands[1 - position][1]
            if _temporal_numeric_pair(operand_type, other_type):
                continue
            context.errors.append(
                Diagnostic(
                    code=DiagnosticCode.OPERAND_NOT_NUMERIC,
                    message=(
                        f"Only integer and real allowed for this operator {expr.op}; "
                        f"{_describe_operand(operand)} is of type {operand_type}"
                    ),
                    span=_operand_span(expr, operand),
                )
            )
        return

    for operand, operand_type in operands:
        if operand_type is None or is_anytype_datatype(operand_type) or is_numeric(operand_type):
            continue
        context.errors.append(
            Diagnostic(
                code=DiagnosticCode.OPERAND_NOT_NUMERIC,
                message=(
                    f"Only integer and real allowed for this operator {expr.op}; "
                    f"{_describe_operand(operand)} is of type {operand_type}"
                ),
                span=_operand_span(expr, operand),
            )
        )


def _describe_operand(operand: SLExpression) -> str:
    """Name an operand in a diagnostic sentence, using its source name when it has one."""
    return f"operand {operand.name!r}" if isinstance(operand, VarRef) else "operand"


def _operand_span(expr: Compare | BinOp, operand: SLExpression) -> SourceSpan | None:
    """Span of one operand, falling back to the enclosing expression."""
    span = _expression_span(operand)
    return span if span is not None else _expression_span(expr)


def _check_bool_operand(expr: BoolOp | NotOp, context: ValidationContext) -> None:
    """Logical operators require boolean operands."""
    operands = expr.operands if isinstance(expr, BoolOp) else (expr.operand,)
    operator = expr.op if isinstance(expr, BoolOp) else "NOT"
    for operand in operands:
        operand_type = infer_expr_type(operand, context.scope, context.records, context.type_graph)
        if operand_type is None or is_anytype_datatype(operand_type) or is_boolean(operand_type):
            continue
        context.errors.append(
            Diagnostic(
                code=DiagnosticCode.LOGICAL_OPERAND_NOT_BOOLEAN,
                message=f"Logical operator {operator!r} expects boolean operands but got {operand_type!r}",
                span=_expression_span(expr),
            )
        )


def _check_unary_operand(expr: UnaryOp, context: ValidationContext) -> None:
    """Unary plus and minus require a numeric operand."""
    operand_type = infer_expr_type(expr.operand, context.scope, context.records, context.type_graph)
    if operand_type is None or is_anytype_datatype(operand_type) or is_numeric(operand_type):
        return
    context.errors.append(
        Diagnostic(
            code=DiagnosticCode.OPERAND_NOT_NUMERIC,
            message=f"Unary operator {expr.op!r} expects a numeric operand but got {operand_type!r}",
            span=_expression_span(expr),
        )
    )


def _check_ternary_branches(expr: TernaryOp, context: ValidationContext) -> None:
    """IF-expression branches must have compatible datatypes.

    An ``AnyType`` branch proves nothing about the value, so it is left out of
    the merge instead of making the branch types look incompatible. The same
    exemption applies to assignment, operand, logical, and condition checks.
    """
    branch_types = [
        infer_expr_type(value, context.scope, context.records, context.type_graph)
        for _condition, value in expr.branches
    ]
    if expr.else_expr is not None:
        branch_types.append(infer_expr_type(expr.else_expr, context.scope, context.records, context.type_graph))
    known_types = [datatype for datatype in branch_types if datatype is not None and not is_anytype_datatype(datatype)]
    if len(known_types) < 2 or merge_compatible_types(known_types) is not None:
        return
    joined = ", ".join(sorted(set(known_types)))
    context.errors.append(
        Diagnostic(
            code=DiagnosticCode.TERNARY_BRANCH_TYPES_INCOMPATIBLE,
            message=f"IF-expression branches must have compatible datatypes; got {joined}",
            span=_expression_span(expr),
        )
    )


def _check_condition(condition: SLExpression, context: ValidationContext, *, construct: str = "IF-sentence") -> None:
    """A condition must be boolean.

    The construct named in the sentence is the IF family by default. An SFC
    transition guard uses the same rule, so its sentence names the guard rather
    than an IF that is not there. ``AnyType`` is exempt, like every other type
    rule that sees it.
    """
    condition_type = infer_expr_type(condition, context.scope, context.records, context.type_graph)
    if condition_type is not None and not is_boolean(condition_type) and not is_anytype_datatype(condition_type):
        context.errors.append(
            Diagnostic(
                code=DiagnosticCode.CONDITION_NOT_BOOLEAN,
                message=f"Condition in {construct} is not boolean; condition is of type {condition_type}",
                span=_expression_span(condition),
            )
        )


def _expression_span(expr: SLExpression) -> SourceSpan | None:
    """Span of a parsed expression node; primitives carry none."""
    span = getattr(expr, "span", None)
    return span if isinstance(span, SourceSpan) else None


def _check_assignment(assignment: Assignment, context: ValidationContext) -> None:
    resolved = resolve_var(assignment.target, context.scope, context.records)
    if resolved is None:
        if _is_sfc_runtime_accessor(assignment.target, context.sfc_names, context.sfc_accessors):
            return
        if unresolved_reference_is_a_defect(assignment.target, context.scope, context.type_graph):
            context.errors.append(
                Diagnostic(
                    code=DiagnosticCode.UNDEFINED_VARIABLE,
                    message=f"Assignment to undefined variable {assignment.target.name!r}",
                    span=assignment.span,
                )
            )
        return
    if is_const_reference(assignment.target, context.scope, context.records):
        context.errors.append(
            Diagnostic(
                code=DiagnosticCode.WRITE_TO_CONST_VARIABLE,
                message=f"Cannot assign to Const variable {assignment.target.name} in module code",
                span=assignment.span,
            )
        )
    check_old_new(assignment.target, bool(resolved.state), context.errors)
    _check_old_write_target(assignment.target, resolved, context.errors)
    if resolved.datatype == ScalarDatatype.STRING:
        # Scope: plain ``String`` only. The other string families
        # (``IdentString``, ``TagString``, ``MaxString``, ``LineString``) are
        # grouped with it for compatibility, but nothing establishes that the
        # language forbids assigning to them directly, so they stay silent.
        # See docs/validation.md, "Open questions".
        context.errors.append(
            Diagnostic(
                code=DiagnosticCode.STRING_ASSIGNMENT_NOT_ALLOWED,
                message=(
                    f"Cannot assign to string variable {resolved.name}; use CopyString() or CopyVar() to copy strings"
                ),
                span=assignment.span,
            )
        )
    target_type, source_type = assignment_types(assignment, context.scope, context.records, context.type_graph)
    if target_type is not None and source_type is not None and not assignment_type_matches(source_type, target_type):
        context.errors.append(
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


def check_old_new(ref: VarRef, is_state: bool | None, errors: list[Diagnostic]) -> None:
    """``:Old``/``:New`` require a resolved State declaration.

    ``is_state`` is ``None`` when the reference does not resolve, in which case
    the reference is unproven and another rule owns the problem. A resolved
    non-State declaration is the finding.
    """
    if ref.state not in ("old", "new"):
        return
    if is_state is None or is_state:
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


def _check_procedure_value_position(call: FuncCall, context: ValidationContext) -> None:
    """A known procedure returns no value, so a value position is rejected.

    The catalogue records a call's ``kind`` separately from its return type, and
    a procedure carries no return type. ``infer_expression_datatype`` treats that
    ``None`` as unproven, which is right for an unknown callee but wrong for a
    known procedure: the callee cannot supply a value in an assignment source, a
    condition, an operand, a ternary branch, or a call argument. Only a resolved
    procedure is reported; an unknown callee stays silent.
    """
    signature = builtin_function_signature(call.name)
    if signature is None or signature.kind != "procedure":
        return
    context.errors.append(
        Diagnostic(
            code=DiagnosticCode.PROCEDURE_IN_VALUE_POSITION,
            message=(
                f"Built-in {signature.name} is a procedure and returns no value; "
                "its call cannot be used where a value is required"
            ),
            span=call.span,
        )
    )


def _check_call(call: FuncCall, context: ValidationContext) -> None:
    signature = builtin_function_signature(call.name)
    for position, arg in enumerate(call.args, start=1):
        if isinstance(arg, str) and not _accepts_string_literal(signature, position):
            context.errors.append(
                Diagnostic(
                    code=DiagnosticCode.STRING_LITERAL_CALL_ARGUMENT,
                    message=f"String literal argument {arg!r} is not allowed in call to {call.name}",
                    span=call.span,
                )
            )
    if signature is None:
        return
    if (
        signature.min_args is not None
        and signature.max_args is not None
        and not signature.min_args <= len(call.args) <= signature.max_args
    ):
        expected = (
            str(signature.min_args)
            if signature.min_args == signature.max_args
            else f"{signature.min_args}..{signature.max_args}"
        )
        context.errors.append(
            Diagnostic(
                code=DiagnosticCode.BUILTIN_WRONG_ARITY,
                message=(f"Built-in {signature.name} expects {expected} arguments but was given {len(call.args)}"),
                span=call.span,
            )
        )
    for position, parameter in enumerate(signature.parameters, start=1):
        index = position - 1
        if index >= len(call.args):
            continue
        arg = call.args[index]
        is_write = parameter.direction in {"out", "inout"}
        # A string-cursor parameter (`accepts_const_string`) names a string
        # buffer rather than a data destination, so a Const string is accepted
        # there. The same reasoning exempts a builtin parameter that names the
        # object member the call writes (see `_OBJECT_WRITE_PARAMETERS`). Both
        # exemptions cover the Const-write finding only: the argument is still
        # checked for being a reference and for its datatype.
        const_exempt = parameter.accepts_const_string or _is_object_write_parameter(signature.name, parameter.name)
        if isinstance(arg, VarRef):
            if is_write:
                resolved = resolve_var(arg, context.scope, context.records)
                if (
                    resolved is not None
                    and is_const_reference(arg, context.scope, context.records)
                    and not const_exempt
                ):
                    context.errors.append(
                        Diagnostic(
                            code=DiagnosticCode.WRITE_TO_CONST_VARIABLE,
                            message=(
                                f"Cannot use Const variable {arg.name!r} as output argument {position} "
                                f"of built-in {signature.name}"
                            ),
                            span=call.span,
                        )
                    )
                _check_old_write_target(arg, resolved, context.errors)
        elif is_write:
            context.errors.append(
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
        elif parameter.direction == "in var":
            context.errors.append(
                Diagnostic(
                    code=DiagnosticCode.BUILTIN_ARG_NOT_VARIABLE,
                    message=(
                        f"Argument {position} of built-in {signature.name} must be a variable reference "
                        f"because parameter {parameter.name!r} is 'in var'"
                    ),
                    span=call.span,
                )
            )
            continue
        actual_type = infer_expr_type(arg, context.scope, context.records, context.type_graph)
        if actual_type is not None and not builtin_type_matches(
            actual_type, parameter.datatype, direction=parameter.direction
        ):
            context.errors.append(
                Diagnostic(
                    code=DiagnosticCode.BUILTIN_ARG_TYPE_MISMATCH,
                    message=(
                        f"Argument {position} of built-in {signature.name} has datatype {actual_type!r} "
                        f"but parameter {parameter.name!r} expects {parameter.datatype!r}"
                    ),
                    span=call.span,
                )
            )


#: Builtin parameters that write a value into an object the call addresses,
#: rather than assigning a caller variable. The argument is the value written
#: into the object, so a Const reference there is not a caller write and
#: `SL-V007` does not apply. `setioattribute`'s `Variable` parameter (position
#: 6, catalogue type `AnyType`) is the only established case: the call targets an
#: I/O object by module, node, board, and channel, and writes the supplied value
#: into that object. The exemption is per builtin and per parameter name, not a
#: blanket `inout` exemption, so every other output argument keeps the rule.
_OBJECT_WRITE_PARAMETERS: dict[str, frozenset[str]] = {
    fold_identifier("setioattribute"): frozenset({fold_identifier("Variable")}),
}


def _is_object_write_parameter(builtin_name: str, parameter_name: str) -> bool:
    """Whether this builtin parameter names an object member written by the call."""
    parameters = _OBJECT_WRITE_PARAMETERS.get(fold_identifier(builtin_name))
    return parameters is not None and fold_identifier(parameter_name) in parameters


def _accepts_string_literal(signature: BuiltinFunction | None, position: int) -> bool:
    """Whether the resolved signature documents a value position for a string literal.

    A literal is a value, so it is accepted only where the documented parameter
    is an ``in`` parameter of a string datatype: ``LoggedIn`` declares its
    user-name parameter that way, so ``LoggedIn("operator")`` passes. A written
    position (``in var``, ``out``, ``inout``) names a buffer that the call fills
    or advances, so a literal there is still rejected, and an unknown callee
    proves nothing, so its literal stays rejected too.
    """
    if signature is None or position > len(signature.parameters):
        return False
    parameter = signature.parameters[position - 1]
    return parameter.direction == "in" and is_string_simple_type(parameter.datatype)


def _is_sfc_runtime_accessor(ref: VarRef, sfc_names: set[str], sfc_accessors: dict[str, frozenset[str]]) -> bool:
    """Whether *ref* is a dotted runtime field of a known SFC element.

    A root declared in the current module uses its element-kind set, so
    ``Step.X`` and ``Seq.Hold`` are accessors while ``Seq.X`` and ``Step.Foo``
    are not. A root visible only program-wide (a sequence in a nested frame
    module) has no element-kind entry here, so the generic accessor names
    apply.
    """
    root, separator, suffix = ref.name.partition(".")
    if not separator or "." in suffix:
        return False
    key = fold_identifier(root)
    allowed = sfc_accessors.get(key)
    if allowed is not None:
        return suffix.casefold() in allowed
    return key in sfc_names and suffix.casefold() in _SFC_ACCESSOR_SUFFIXES


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
        elif isinstance(item, (SFCTransition, SFCTransitionSub)):
            if item.name is not None:
                transition_names.add(fold_identifier(item.name))
            if isinstance(item, SFCTransitionSub):
                _collect_jump_targets(item.body, step_names, transition_names)
        elif isinstance(item, (SFCAlternative, SFCParallel)):
            for branch in item.branches:
                _collect_jump_targets(branch, step_names, transition_names)
        elif isinstance(item, SFCSubsequence):
            if item.kind == "substep" and item.name is not None:
                step_names.add(fold_identifier(item.name))
            _collect_jump_targets(item.body, step_names, transition_names)


def _collect_module_sfc_name_counts(sequences: list[Sequence] | None) -> dict[str, int]:
    """Count every named SFC element across the module code block."""
    counts: dict[str, int] = {}
    for sequence in sequences or ():
        _count_sfc_names(sequence.code, counts)
    return counts


def _count_sfc_names(items: list[SFCBodyItem], counts: dict[str, int]) -> None:
    for item in items:
        name = _named_sfc_element_name(item)
        if name is not None:
            folded = fold_identifier(name)
            counts[folded] = counts.get(folded, 0) + 1
        if isinstance(item, (SFCAlternative, SFCParallel)):
            for branch in item.branches:
                _count_sfc_names(branch, counts)
        elif isinstance(item, (SFCSubsequence, SFCTransitionSub)):
            _count_sfc_names(item.body, counts)


def _check_fork_targets(
    items: list[SFCBodyItem],
    step_names: set[str],
    transition_names: set[str],
    name_counts: dict[str, int],
    errors: list[Diagnostic],
) -> None:
    """Resolve every SEQFORK target and check its kind.

    Unresolved or wrong-kind targets are rejected. A fork hosted on a step must
    name transitions, and a fork hosted on a transition must name steps; a rule
    that merely required every target to be a step would be wrong. A target
    declared more than once is ambiguous before either kind rule applies.
    """

    def _check_fork(fork: SFCFork | None, host: str, span: SourceSpan | None) -> None:
        if fork is None:
            return
        expected = transition_names if host == "step" else step_names
        other = step_names if host == "step" else transition_names
        expected_kind = "transition" if host == "step" else "step"
        for target in fork.targets:
            folded = fold_identifier(target)
            if name_counts.get(folded, 0) > 1:
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.SEQUENCE_AMBIGUOUS_FORK_TARGET,
                        message=f"SEQFORK target {target!r} is declared more than once in the module",
                        span=span,
                    )
                )
                continue
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
        elif isinstance(item, (SFCAlternative, SFCParallel)):
            for branch in item.branches:
                _check_fork_targets(branch, step_names, transition_names, name_counts, errors)
        elif isinstance(item, (SFCSubsequence, SFCTransitionSub)):
            _check_fork_targets(item.body, step_names, transition_names, name_counts, errors)


def _check_duplicate_sfc_names(sequences: list[Sequence] | None, errors: list[Diagnostic]) -> None:
    """Flag step and transition names that are reused within a module code block."""
    seen: set[str] = set()
    for sequence in sequences or ():
        _record_module_names(sequence.code, seen, errors)


def _record_module_names(items: list[SFCBodyItem], seen: set[str], errors: list[Diagnostic]) -> None:
    for item in items:
        name = _named_step_or_transition_name(item)
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
        if isinstance(item, (SFCAlternative, SFCParallel)):
            for branch in item.branches:
                _record_module_names(branch, seen, errors)
        elif isinstance(item, (SFCSubsequence, SFCTransitionSub)):
            _record_module_names(item.body, seen, errors)


def _named_sfc_element_name(item: SFCBodyItem) -> str | None:
    """Name of any SFC element that can be a ``SEQFORK`` target."""
    if isinstance(item, SFCSubsequence):
        return item.name
    if isinstance(item, (SFCStep, SFCTransition, SFCTransitionSub)):
        return item.name
    return None


def _named_step_or_transition_name(item: SFCBodyItem) -> str | None:
    """Name in the step/transition namespace guarded by ``SL-V021``.

    ``SFCSubsequence`` (``SUBSEQUENCE`` / ``SUBSEQSTEP``) and
    ``SFCTransitionSub`` (``SUBSEQTRANSITION``) name a wrapper around a nested
    body, not a step or transition in the module's element table. A wrapper may
    therefore reuse the name of an element inside its own body.
    """
    if isinstance(item, (SFCStep, SFCTransition)):
        return item.name
    return None
