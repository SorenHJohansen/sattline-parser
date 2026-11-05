"""The rule registry: one entry for every diagnostic code.

The registry is the single source of truth for a rule's identity, scope,
availability, and prose. It does not run rules; the validator
still owns execution. Keeping the metadata here lets the CLI, the documentation
table, and the completeness tests agree without copying the enum.

A rule is ``active`` when the validator emits it, ``retired`` when the form was
proved to load and the check was withdrawn, and ``unimplemented`` when a code
was reserved but no check exists yet. Retired and unimplemented rules stay in
the registry so stored diagnostics and code references remain valid.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import StrEnum

from sattline_parser.validation.diagnostics import DiagnosticCode

__all__ = [
    "RETIRED_CODES",
    "RULES",
    "RULES_BY_CODE",
    "RULES_BY_ID",
    "RULES_BY_NAME",
    "Rule",
    "RuleScope",
    "RuleStatus",
    "UnknownRuleError",
    "find_rule",
    "render_markdown_table",
    "require_rule",
]

_UNIMPLEMENTED_NOTE = "Declared as a diagnostic code, but the current validator does not emit it."


class RuleScope(StrEnum):
    """The part of the language a rule inspects."""

    DECLARATIONS = "declarations"
    CODE = "code"
    SFC = "sfc"
    MAPPINGS = "mappings"
    PROJECT = "project"


class RuleStatus(StrEnum):
    """Whether a rule is emitted, withdrawn, or reserved."""

    ACTIVE = "active"
    RETIRED = "retired"
    UNIMPLEMENTED = "unimplemented"


@dataclass(frozen=True, slots=True)
class Rule:
    """Metadata for one diagnostic code.

    ``code`` is the stable identity. ``id`` and ``name`` are derived from it, so
    the registry cannot drift from the enum. ``details`` carries the longer
    explanation, including the reason a rule is retired or unimplemented.
    """

    code: DiagnosticCode
    summary: str
    scope: RuleScope = RuleScope.DECLARATIONS
    implemented: bool = True
    retired: bool = False
    details: str | None = None

    @property
    def id(self) -> str:
        """The machine identifier, for example ``SL-V019``."""
        return self.code.value

    @property
    def name(self) -> str:
        """The enum name, for example ``UNDEFINED_VARIABLE``."""
        return self.code.name

    @property
    def status(self) -> RuleStatus:
        """Whether the rule is emitted, retired, or reserved."""
        if self.retired:
            return RuleStatus.RETIRED
        if not self.implemented:
            return RuleStatus.UNIMPLEMENTED
        return RuleStatus.ACTIVE

    @property
    def enabled(self) -> bool:
        """True when the validator may emit this rule."""
        return self.status is RuleStatus.ACTIVE

    def to_json(self) -> dict[str, object]:
        """The CLI shape for ``sattline rules --json``."""
        return {
            "id": self.id,
            "name": self.name,
            "scope": self.scope.value,
            "status": self.status.value,
            "retired": self.retired,
            "summary": self.summary,
            "details": self.details,
        }


def _rule(
    code: DiagnosticCode,
    summary: str,
    *,
    scope: RuleScope,
    implemented: bool = True,
    retired: bool = False,
    details: str | None = None,
) -> Rule:
    return Rule(
        code=code,
        summary=summary,
        scope=scope,
        implemented=implemented,
        retired=retired,
        details=details,
    )


#: Every diagnostic code, in enum order.
RULES: tuple[Rule, ...] = (
    _rule(
        DiagnosticCode.DUPLICATE_DATATYPE_NAME,
        "A datatype name may be declared twice.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="A datatype name may be declared twice; the source loads and parses.",
    ),
    _rule(
        DiagnosticCode.DUPLICATE_MODULETYPE_NAME,
        "A module-type name may be declared twice.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="A module-type name may be declared twice; the source loads and parses.",
    ),
    _rule(
        DiagnosticCode.DUPLICATE_VARIABLE_NAME,
        "A variable name may be declared twice.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="A variable name may be declared twice; the source loads and parses.",
    ),
    _rule(
        DiagnosticCode.DUPLICATE_SIBLING_SUBMODULE,
        "Two sibling submodule instances may not share a name.",
        scope=RuleScope.DECLARATIONS,
    ),
    _rule(
        DiagnosticCode.OLD_NEW_ON_NON_STATE_VARIABLE,
        "`:Old` and `:New` require a State variable.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.OLD_NEW_ON_NON_STATE_FIELD,
        "`:Old` and `:New` require a State record field.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.WRITE_TO_CONST_VARIABLE,
        "A Const variable may not be assigned or written through an output argument.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.INIT_VALUE_TYPE_MISMATCH,
        "An initial value must match its variable's datatype.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="An init value may have a different datatype from its variable; the source loads.",
    ),
    _rule(
        DiagnosticCode.BARE_DURATION_INIT,
        "A duration variable needs a duration literal, not a bare string.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="A duration variable may be initialized with a bare string; the source loads.",
    ),
    _rule(
        DiagnosticCode.BARE_TIME_INIT,
        "A time variable needs a time literal, not a bare string.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="A time variable may be initialized with a bare string; the source loads.",
    ),
    _rule(
        DiagnosticCode.MALFORMED_DURATION_LITERAL,
        "A duration literal must be well formed.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="An invalid duration literal may load; the editor guard is not a parser rule.",
    ),
    _rule(
        DiagnosticCode.MALFORMED_TIME_LITERAL,
        "A time literal must be well formed.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="An invalid time literal may load; the editor guard is not a parser rule.",
    ),
    _rule(
        DiagnosticCode.BUILTIN_WRONG_ARITY,
        "A builtin call must supply between its minimum and maximum argument count.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.BUILTIN_OUT_ARG_NOT_VARIABLE,
        "A builtin output argument must be a plain variable reference.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.STRING_LITERAL_CALL_ARGUMENT,
        "A string literal may not stand in a call argument position that requires a reference.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS,
        "SFC steps must be separated by a transition.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.SEQUENCE_FORK_UNKNOWN_TARGET,
        "A SEQFORK target must name an SFC element in the module.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.BUILTIN_DATATYPE_TYPO,
        "A near miss of a builtin datatype name is reported as a typo.",
        scope=RuleScope.DECLARATIONS,
    ),
    _rule(
        DiagnosticCode.UNDEFINED_VARIABLE,
        "A reference or assignment target must resolve to a declared variable or parameter.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.UNKNOWN_DATATYPE_NAME,
        "A datatype reference must resolve to a builtin or a declared DATATYPE.",
        scope=RuleScope.DECLARATIONS,
    ),
    _rule(
        DiagnosticCode.DUPLICATE_SFC_ELEMENT_NAME,
        "SFC step and transition names must be unique within a module.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.SFC_INIT_STEP_PLACEMENT,
        "A sequence must contain exactly one init step in a valid position.",
        scope=RuleScope.SFC,
        retired=True,
        details="A sequence may omit or misplace its init step; the source loads.",
    ),
    _rule(
        DiagnosticCode.SFC_ALTERNATIVE_BRANCH_START,
        "An ALTERNATIVESEQ branch must start with a SEQTRANSITION.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.SFC_PARALLEL_BRANCH_START,
        "A PARALLELSEQ branch must start and end with a SEQSTEP.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.DUPLICATE_RECORD_FIELD_NAME,
        "A record may not declare the same field name twice.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="A record field may be declared twice; the source loads.",
    ),
    _rule(
        DiagnosticCode.BUILTIN_DATATYPE_SHADOWED,
        "A declaration may not reuse a builtin datatype name.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="A declaration may reuse a builtin datatype name; the source loads.",
    ),
    _rule(
        DiagnosticCode.PARAM_TRANSFER_TYPE_MISMATCH,
        "A submodule argument must be type compatible with the declared module-type parameter.",
        scope=RuleScope.MAPPINGS,
    ),
    _rule(
        DiagnosticCode.OPERAND_NOT_NUMERIC,
        "Arithmetic and unary operators require integer or real operands.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.ASSIGNMENT_TYPE_MISMATCH,
        "An assigned value must have a datatype compatible with the target.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.CONDITION_NOT_BOOLEAN,
        "IF, ELSIF, WAIT_FOR, and Enable_ tail conditions must be boolean.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.ATTRIBUTE_COMBINATION_INVALID,
        "Declaration attributes must appear in an accepted order and combination.",
        scope=RuleScope.DECLARATIONS,
    ),
    _rule(
        DiagnosticCode.COORDINATE_NOT_REAL,
        "A coordinate value must be real.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.SEQUENCE_ENDS_WITH_STEP,
        "A closed sequence must end with a transition, not a step.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.RESERVED_NAME_DECLARED,
        "`On` and `Off` may not be declared.",
        scope=RuleScope.DECLARATIONS,
        retired=True,
        details="The grammar rejects `On`/`Off` at a declaration position, exactly like `True`/`False`; the code stays reserved.",
    ),
    _rule(
        DiagnosticCode.OLD_STATE_NOT_WRITABLE,
        "The `:Old` state of a State variable is read-only.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.SEQUENCE_POSITION_INVALID,
        "SFC steps, transitions, and structural constructs must occupy valid positions.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.SEQUENCE_FORK_TARGET_KIND,
        "A SEQFORK on a step must target a transition, and the reverse.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.IDENTIFIER_TOO_LONG,
        "A declared identifier may be at most 20 characters.",
        scope=RuleScope.DECLARATIONS,
    ),
    _rule(
        DiagnosticCode.RESERVED_KEYWORD_NAME,
        "A declaration may not use a reserved SattLine keyword as its name.",
        scope=RuleScope.DECLARATIONS,
    ),
    _rule(
        DiagnosticCode.DATATYPE_TOO_FEW_FIELDS,
        "A DATATYPE declaration must declare at least one field.",
        scope=RuleScope.DECLARATIONS,
        implemented=False,
        details=_UNIMPLEMENTED_NOTE,
    ),
    _rule(
        DiagnosticCode.COMPARE_INCOMPATIBLE_OPERANDS,
        "Comparison operators require compatible operand datatypes.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.DIVISION_BY_ZERO,
        "Division by a literal zero is rejected.",
        scope=RuleScope.CODE,
        implemented=False,
        details=_UNIMPLEMENTED_NOTE,
    ),
    _rule(
        DiagnosticCode.LOGICAL_OPERAND_NOT_BOOLEAN,
        "Logical operators require boolean operands.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.TERNARY_BRANCH_TYPES_INCOMPATIBLE,
        "IF-expression branches must have compatible datatypes.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.STRING_ASSIGNMENT_NOT_ALLOWED,
        "A string variable is copied with CopyString or CopyVar, not assigned directly.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.BUILTIN_ARG_NOT_VARIABLE,
        "An `in var` builtin parameter requires a variable reference argument.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.BUILTIN_ARG_TYPE_MISMATCH,
        "A builtin argument must match its declared parameter datatype.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.PARAMETER_MAPPING_TARGET_UNKNOWN,
        "A module-type instance mapping must target a declared parameter.",
        scope=RuleScope.MAPPINGS,
    ),
    _rule(
        DiagnosticCode.PARAMETER_MAPPING_DUPLICATE_TARGET,
        "A module-type instance may map each parameter target only once.",
        scope=RuleScope.MAPPINGS,
    ),
    _rule(
        DiagnosticCode.PARAMETER_MAPPING_TYPE_MISMATCH,
        "A module-type instance mapping value must match the parameter datatype.",
        scope=RuleScope.MAPPINGS,
    ),
    _rule(
        DiagnosticCode.STEP_AUTO_VARIABLE_UNAVAILABLE,
        "A step or sequence accessor requires the matching SeqControl or SeqTimer flag.",
        scope=RuleScope.CODE,
    ),
    _rule(
        DiagnosticCode.SEQUENCE_TRANSITION_AFTER_TRANSITION,
        "A transition may not directly follow another transition.",
        scope=RuleScope.SFC,
        implemented=False,
        details=_UNIMPLEMENTED_NOTE,
    ),
    _rule(
        DiagnosticCode.PARALLEL_BRANCH_INCOMPLETE,
        "A parallel branch must contain a complete step sequence.",
        scope=RuleScope.SFC,
        implemented=False,
        details=_UNIMPLEMENTED_NOTE,
    ),
    _rule(
        DiagnosticCode.SUBSEQTRANSITION_STARTS_WITH_STEP,
        "A SUBSEQTRANSITION body must not start with a step.",
        scope=RuleScope.SFC,
        implemented=False,
        details=_UNIMPLEMENTED_NOTE,
    ),
    _rule(
        DiagnosticCode.SEQUENCE_REQUIRES_INIT_STEP,
        "A closed sequence must contain an init step.",
        scope=RuleScope.SFC,
        implemented=False,
        details=_UNIMPLEMENTED_NOTE,
    ),
    _rule(
        DiagnosticCode.SEQUENCE_AMBIGUOUS_FORK_TARGET,
        "A SEQFORK target may not be declared more than once in a module.",
        scope=RuleScope.SFC,
    ),
    _rule(
        DiagnosticCode.DATECODE_CONFLICT,
        "The same module type or datatype may not be declared with different datecodes in a visible closure.",
        scope=RuleScope.PROJECT,
    ),
    _rule(
        DiagnosticCode.UNKNOWN_MODULETYPE_NAME,
        "A module-type instance must name a declared type or one visible from a loaded dependency.",
        scope=RuleScope.PROJECT,
    ),
)

RULES_BY_CODE: dict[DiagnosticCode, Rule] = {rule.code: rule for rule in RULES}
RULES_BY_ID: dict[str, Rule] = {rule.id.casefold(): rule for rule in RULES}
RULES_BY_NAME: dict[str, Rule] = {rule.name.casefold(): rule for rule in RULES}

#: Retired rules and the reason they are not enforced. Kept as a mapping for
#: callers that predate the registry.
RETIRED_CODES: dict[DiagnosticCode, str] = {rule.code: rule.details or rule.summary for rule in RULES if rule.retired}


class UnknownRuleError(ValueError):
    """A rule name or id does not resolve to a registry entry."""

    def __init__(self, value: str) -> None:
        self.value = value
        close = difflib.get_close_matches(
            value.casefold(),
            [*RULES_BY_ID, *RULES_BY_NAME],
            n=3,
            cutoff=0.55,
        )
        suggestions = sorted(
            {rule.name for match in close if (rule := RULES_BY_ID.get(match) or RULES_BY_NAME.get(match)) is not None}
        )
        suggestion = f"; did you mean {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(f"unknown rule {value!r}{suggestion}")


def find_rule(value: str) -> Rule | None:
    """Resolve a rule by ``SL-V###`` id or by enum name, case-insensitively."""
    key = value.casefold()
    return RULES_BY_ID.get(key) or RULES_BY_NAME.get(key)


def require_rule(value: str) -> Rule:
    """Resolve a rule, raising :class:`UnknownRuleError` when it is absent."""
    rule = find_rule(value)
    if rule is None:
        raise UnknownRuleError(value)
    return rule


def render_markdown_table(*, include_retired: bool = True) -> str:
    """Render the registry as a Markdown table, in enum order.

    ``docs/validation.md`` embeds this output between markers and a test asserts
    the two agree, so the documentation table cannot drift from the enum.
    """
    lines = [
        "| Id | Name | Status | Scope | Summary |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rule in RULES:
        if rule.retired and not include_retired:
            continue
        lines.append(f"| `{rule.id}` | `{rule.name}` | {rule.status.value} | {rule.scope.value} | {rule.summary} |")
    return "\n".join(lines)
