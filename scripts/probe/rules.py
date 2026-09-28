"""Probe definitions for real-parser conformance probing.

Each :class:`Probe` expands to one or more program/library *units* in
``probes/rules/``. Every unit is a triple — ``.s`` source + ``.y`` graphics +
``.z`` dependency list — because the real tool refuses to parse a program or
library without its three files. A *control* unit exercises a construct
(believed valid); *violation* units break it in exactly one way. Text
mutations are applied to the corpus base fixtures or inline templates, so
mutations must be exact and unique — :mod:`generate` fails loudly otherwise.

Expected outcomes are hypotheses; the real parser decides. ``expected`` values:
``accept`` / ``reject`` / ``unknown``. The graphics/deps probes (C-201/C-202)
differ only in the generated ``.y``, keeping the code ``.s`` identical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "corpus"
VALID = CORPUS / "valid"
EDGE = CORPUS / "edge_cases"


def _once(text: str, old: str) -> None:
    if text.count(old) != 1:
        raise AssertionError(f"expected exactly one occurrence of {old!r}, found {text.count(old)}")


def replace_line(match: str, replacement: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        _once(text, match)
        return text.replace(match, replacement)

    return apply


def insert_after(match: str, insertion: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        _once(text, match)
        return text.replace(match, match + insertion, 1)

    return apply


def identity() -> Callable[[str], str]:
    def apply(text: str) -> str:
        return text

    return apply


@dataclass(frozen=True)
class ProbeFile:
    """One emitted program/library unit (``.s`` + ``.y`` + ``.z``) within a probe.

    ``mutate`` transforms the base ``.s`` source. The companion graphics (``.y``)
    and dependency (``.z``) files are generated from the code's first-line date
    and ``z``; ``y`` selects the graphics variant (see ``generate``):
    ``"default"`` (matches the code date), ``"shift-date"`` (one day later) or
    ``"extra-object"`` (one extra composite object).
    """

    name: str
    kind: str  # "control" | "violation"
    expected: str  # "accept" | "reject" | "unknown"
    intent: str
    mutate: Callable[[str], str] = field(repr=False, default=identity())
    y: str = "default"  # graphics variant: "default" | "shift-date" | "extra-object"
    z: tuple[str, ...] = ("StdLib",)  # dependency list written to the .z


@dataclass(frozen=True)
class Probe:
    id: str
    tier: int
    area: str
    summary: str
    base: str | None  # corpus prefix ('' | 'valid' | 'edge_cases') or None for inline template
    files: tuple[ProbeFile, ...]
    note: str = ""

    @property
    def base_path(self) -> Path:
        if not self.base:
            raise ValueError("template probes have no base")
        prefix, stem = self.base.split(":")
        return {VALID.name: VALID, EDGE.name: EDGE}[prefix] / f"{stem}.s"


# ---------------------------------------------------------------------------
# Moduletype/loop inline templates (C-101 / C-102).
# Real-style (observed in Libs/): moduletypes are ``Name = MODULEDEFINITION
# DateCode_ <hash>`` and instances bind by name (same unit) or by
# ``: MODULEDEFINITION DateCode_ <hash> ( Name )`` (cross-unit). Synthetic
# hashes use a 9xxxxx / 10x namespace so they are never confused with real
# content hashes.
# ---------------------------------------------------------------------------

_HEADER = """\
"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: {name}"
"""

_PIC_DATECODE = 900001
_LEAF_DATECODE = 101300
_TYPE_A_DATECODE = 101100
_TYPE_B_DATECODE = 101200


def _picture(name: str, typedefs: str, top_localvars: str) -> str:
    return (
        _HEADER.format(name=name)
        + "\n"
        + "BasePicture Invocation\n"
        + "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        + f"    ) : MODULEDEFINITION DateCode_ {_PIC_DATECODE}\n"
        + "\n"
        + "TYPEDEFINITIONS\n"
        + typedefs
        + "\n"
        + "LOCALVARIABLES\n"
        + top_localvars
        + "\n"
        + "ModuleDef\n"
        + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "\n"
        + "ENDDEF (*BasePicture*);\n"
    )


_LEAF = f"""\
   LeafType = MODULEDEFINITION DateCode_ {_LEAF_DATECODE}
   LOCALVARIABLES
      LeafVar: integer  := 0;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK LeafEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      LeafVar = LeafVar + 1;
   ENDDEF (*LeafType*);

"""


def _type_a(binding: str) -> str:
    """TypeA with one child bound to ``binding``: ``: Name`` (same unit) or
    ``: MODULEDEFINITION DateCode_ <N>`` (cross-unit; the parenthesised
    ``Frame_Module`` option is not a name hint, so it is only used on
    picture/frame bindings)."""
    return (
        f"   TypeA = MODULEDEFINITION DateCode_ {_TYPE_A_DATECODE}\n"
        + "   LOCALVARIABLES\n"
        + "      AVar: integer  := 0;\n"
        + "   SUBMODULES\n"
        + "      AChild Invocation\n"
        + "         ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5\n"
        + "          ) "
        + binding
        + ";\n"
        + "   ModuleDef\n"
        + "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        + "   ModuleCode\n"
        + "   EQUATIONBLOCK AEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        + "      AVar = AVar + 1;\n"
        + "   ENDDEF (*TypeA*);\n"
        + "\n"
    )


_TYPE_B = (
    f"   TypeB = MODULEDEFINITION DateCode_ {_TYPE_B_DATECODE}\n"
    + "   LOCALVARIABLES\n"
    + "      BVar: integer  := 0;\n"
    + "   SUBMODULES\n"
    + "      BChild Invocation\n"
    + "         ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5\n"
    + "          ) : TypeA;\n"
    + "   ModuleDef\n"
    + "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    + "   ModuleCode\n"
    + "   EQUATIONBLOCK BEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
    + "      BVar = BVar + 1;\n"
    + "   ENDDEF (*TypeB*);\n"
    + "\n"
)

_SELF_TYPE_A = _type_a(": TypeA")  # same-unit self instance (name-based)
_CHAIN_TYPES = _type_a(": LeafType") + _LEAF  # acyclic: TypeA -> LeafType
_CYCLE_TYPES = _type_a(": TypeB") + _TYPE_B  # cycle: TypeA -> TypeB -> TypeA (same unit, name-based)

_PROBE_TOP_LOCALVARS = "   TopVar: integer  := 0;\n"

# ---------------------------------------------------------------------------
# Probe set.
# ---------------------------------------------------------------------------

PROBES: tuple[Probe, ...] = (
    # ---- Tier 1: validation tier, intra-file (§6.1) ----
    Probe(
        id="T1-001",
        tier=1,
        area="expression-types",
        summary="assignment LHS/RHS type compatibility",
        base="valid:ControlFlow",
        note="hypothesis: real-type assignment from boolean rejected",
        files=(
            ProbeFile("control.s", "control", "accept", "same-type assignments only (baseline)"),
            ProbeFile(
                "violation-int-from-bool.s",
                "violation",
                "reject",
                "integer variable assigned a boolean expression",
                replace_line("         Output = 0;", "         Output = Flag1;"),
            ),
        ),
    ),
    Probe(
        id="T1-002",
        tier=1,
        area="expression-types",
        summary="comparison operand type compatibility",
        base="valid:ControlFlow",
        note="hypothesis: mixed numeric/boolean comparison rejected",
        files=(
            ProbeFile("control.s", "control", "accept", "numeric comparison (baseline)"),
            ProbeFile(
                "violation-real-vs-bool.s",
                "violation",
                "reject",
                "real compared with boolean",
                replace_line(
                    "      Result = IF X > 0.0 THEN X ELSE X + Y ENDIF;",
                    "      Result = IF X > Flag1 THEN X ELSE X + Y ENDIF;",
                ),
            ),
        ),
    ),
    Probe(
        id="T1-003",
        tier=1,
        area="expression-types",
        summary="IF-condition must be boolean",
        base="valid:ControlFlow",
        note="hypothesis: integer used as IF condition rejected",
        files=(
            ProbeFile("control.s", "control", "accept", "boolean conditions (baseline)"),
            ProbeFile(
                "violation-int-condition.s",
                "violation",
                "reject",
                "integer expression as IF condition",
                replace_line("      IF Flag1 THEN", "      IF A THEN"),
            ),
        ),
    ),
    Probe(
        id="T1-004",
        tier=1,
        area="expression-types",
        summary="builtin call argument types (not just count)",
        base="valid:BuiltinCalls",
        note="BuiltinFunction models arity+out-positions only; probe per-arg typing",
        files=(
            ProbeFile("control.s", "control", "accept", "Equal(int, int) (in base fixture)"),
            ProbeFile(
                "violation-string-arg.s",
                "violation",
                "reject",
                "Equal(int, string)",
                replace_line("      IsEqual = Equal(A, B);", "      IsEqual = Equal(A, Template);"),
            ),
        ),
    ),
    Probe(
        id="T1-005",
        tier=1,
        area="expression-types",
        summary="record qualification depth (dotted access beyond record)",
        base="valid:RecordTypeAccess",
        note="hypothesis: scalar-root .field access is rejected",
        files=(
            ProbeFile("control.s", "control", "accept", "nested record field access (in base)"),
            ProbeFile(
                "violation-too-deep.s",
                "violation",
                "reject",
                "field access on a scalar record field",
                replace_line(
                    "      Sensor.Position.X = Sensor.Calibrated;", "      Sensor.Position.X.Y = Sensor.Calibrated;"
                ),
            ),
        ),
    ),
    Probe(
        id="T1-006",
        tier=1,
        area="context-restricted-types",
        summary="AnyType legal only as a module parameter type",
        base="valid:SubmoduleParams",
        note="user-asserted: param OK, record field + localvar rejected. Our parser currently flags AnyType as unknown datatype (SL-V020).",
        files=(
            ProbeFile(
                "anytype-param.s",
                "control",
                "accept",
                "AnyType as a MODULEPARAMETERS type",
                insert_after("      EnableControl: boolean  := False;\n", "      Query: AnyType ;\n"),
            ),
            ProbeFile(
                "anytype-localvar.s",
                "violation",
                "reject",
                "AnyType as a LOCALVARIABLES type",
                insert_after("      Error: real  := 0.0;\n", "      Query: AnyType ;\n"),
            ),
        ),
    ),
    Probe(
        id="T1-006b",
        tier=1,
        area="context-restricted-types",
        summary="AnyType rejected as a record field type",
        base="valid:RecordTypeAccess",
        note="user-asserted; paired with T1-006 control",
        files=(
            ProbeFile("control.s", "control", "accept", "record fields with ordinary types (in base)"),
            ProbeFile(
                "violation-anytype-field.s",
                "violation",
                "reject",
                "AnyType as a RECORD field type",
                insert_after("      X: real  := 0.0;\n      Y: real  := 0.0;\n", "      Probed: AnyType ;\n"),
            ),
        ),
    ),
    Probe(
        id="T1-007",
        tier=1,
        area="statement-context",
        summary=":= Default allowed on all parameters",
        base="valid:SubmoduleParams",
        note="user-asserted: Default legal on all parameters; scalar-localvar Default is the open question",
        files=(
            ProbeFile(
                "control-default-param.s",
                "control",
                "accept",
                "parameter initialized with := Default",
                replace_line("      Gain: real  := 1.0;", "      Gain: real  := Default;"),
            ),
            ProbeFile(
                "violation-default-scalar-localvar.s",
                "violation",
                "unknown",
                "scalar local variable initialized with := Default",
                replace_line("   ProcessSetpoint: real  := 75.0;", "   ProcessSetpoint: real  := Default;"),
            ),
        ),
    ),
    Probe(
        id="T1-008",
        tier=1,
        area="statement-context",
        summary="Const does not require an initializer",
        base="valid:VariableModifiers",
        note="user-asserted: const without init uses type default. Disproves earlier 'const needs init' hypothesis.",
        files=(
            ProbeFile("control-with-init.s", "control", "accept", "Const variable with initializer (in base)"),
            ProbeFile(
                "violation-const-no-init.s",
                "violation",
                "accept",
                "Const variable declared without initializer",
                replace_line("   MaxLimit: integer Const  := 100;", "   MaxLimit: integer Const ;"),
            ),
        ),
    ),
    Probe(
        id="T1-009",
        tier=1,
        area="statement-context",
        summary="modifier legality per datatype (State/OpSave)",
        base="valid:VariableModifiers",
        note="open question: State allowed on integer? OpSave on string?",
        files=(
            ProbeFile("control.s", "control", "accept", "State on boolean, OpSave on real (in base)"),
            ProbeFile(
                "violation-state-int.s",
                "violation",
                "unknown",
                "State modifier on an integer variable",
                insert_after("   ActiveFlag: boolean State  := False;\n", "   IntStateFlag: integer State  := 0;\n"),
            ),
            ProbeFile(
                "violation-opsave-string.s",
                "violation",
                "unknown",
                "OpSave modifier on a string variable",
                insert_after("   OperatorSetpoint: real OpSave  := 50.0;\n", '   StrOpsave: string OpSave  := "";\n'),
            ),
        ),
    ),
    Probe(
        id="T1-010",
        tier=1,
        area="statement-context",
        summary=":Old / :New only on State variables (context: equation block)",
        base="valid:OldNewOnStateField",
        note="corpus already uses :Old/:New inside EQUATIONBLOCK, so 'only in step code' is likely disproven; probes the non-State-target part",
        files=(
            ProbeFile("control.s", "control", "accept", ":Old/:New on State fields inside equations (in base)"),
            ProbeFile(
                "violation-old-on-nonstate.s",
                "violation",
                "reject",
                ":Old read on a non-State record field in an equation",
                insert_after(
                    "      ValveJustOpened = Valve.IsOpen:New AND NOT Valve.IsOpen:Old;\n",
                    "      OpenedThisScan = Valve.Position:Old > 0.0;\n",
                ),
            ),
        ),
    ),
    Probe(
        id="T1-011",
        tier=1,
        area="sfc",
        summary="SFC accessors: Step.X / Step.T / Seq.Reset and their enablement",
        base="valid:SequenceBasic",
        note="user-asserted: accessors legal only when the feature is enabled for the sequence; enabled step names become variables and must not collide. Enablement mechanism TBD — probe pairs the enabled option with accessor usage.",
        files=(
            ProbeFile("control.s", "control", "accept", "sequence with SeqControl,SeqTimer enabled (in base)"),
            ProbeFile(
                "violation-step-accessor.s",
                "violation",
                "accept",
                "Step.X accessor inside the step's ACTIVECODE (feature flag set)",
                insert_after(
                    "            Output = Output + 1;\n",
                    "             IF Running.X THEN\n                Output = Output + 2;\n             ENDIF;\n",
                ),
            ),
            ProbeFile(
                "violation-seq-reset.s",
                "violation",
                "accept",
                "Seq.Reset accessor on the enclosing sequence",
                insert_after("            Output = Output + 1;\n", "             StartCmd = MainSeq.Reset;\n"),
            ),
        ),
    ),
    Probe(
        id="T1-012",
        tier=1,
        area="reserved-names",
        summary="reserved constant names (On/Off/GroupData) as variable identifiers",
        base="valid:MinimalProgram",
        note="our validator exempts On/Off reads but never forbids declaring them",
        files=(
            ProbeFile(
                "control-ordinary-name.s",
                "control",
                "accept",
                "ordinary variable name Switch",
                insert_after(
                    "    ) : MODULEDEFINITION DateCode_ 1\n\n", "LOCALVARIABLES\n   Switch: boolean  := False;\n\n"
                ),
            ),
            ProbeFile(
                "violation-var-on.s",
                "violation",
                "reject",
                "variable named On",
                insert_after(
                    "    ) : MODULEDEFINITION DateCode_ 1\n\n", "LOCALVARIABLES\n   On: boolean  := False;\n\n"
                ),
            ),
            ProbeFile(
                "violation-var-off.s",
                "violation",
                "reject",
                "variable named Off",
                insert_after(
                    "    ) : MODULEDEFINITION DateCode_ 1\n\n", "LOCALVARIABLES\n   Off: boolean  := False;\n\n"
                ),
            ),
            ProbeFile(
                "violation-var-groupdata.s",
                "violation",
                "reject",
                "variable named GroupData",
                insert_after(
                    "    ) : MODULEDEFINITION DateCode_ 1\n\n", "LOCALVARIABLES\n   GroupData: boolean  := False;\n\n"
                ),
            ),
        ),
    ),
    # ---- Reversal watchlist (§6.4) ----
    Probe(
        id="R-101",
        tier=1,
        area="sfc",
        summary="reversal: multiple SEQINITSTEPs (challenges SL-V022)",
        base="valid:SequenceBasic",
        note="user-asserted: unlimited SEQINITSTEPs allowed",
        files=(
            ProbeFile("control-single-init.s", "control", "accept", "a single SEQINITSTEP (in base)"),
            ProbeFile(
                "violation-second-init.s",
                "violation",
                "accept",
                "a second SEQINITSTEP in the same sequence",
                insert_after(
                    "      SEQTRANSITION TrDone WAIT_FOR NOT StopCmd\n",
                    "      SEQINITSTEP IdleAgain\n         ENTERCODE\n            Output = 0;\n",
                ),
            ),
        ),
    ),
    Probe(
        id="R-102",
        tier=1,
        area="sfc",
        summary="reversal: SEQINITSTEP need not be first (challenges SL-V022)",
        base="valid:SequenceBasic",
        note="user-asserted for count; the 'must be first' constraint is probed separately",
        files=(
            ProbeFile("control-init-first.s", "control", "accept", "SEQINITSTEP as the first element (in base)"),
            ProbeFile(
                "violation-init-after-step.s",
                "violation",
                "accept",
                "a SEQSTEP and transition precede the SEQINITSTEP",
                replace_line(
                    "      SEQINITSTEP Idle",
                    "      SEQSTEP WarmUp\n         ENTERCODE\n            Output = -2;\n      SEQTRANSITION TrPre WAIT_FOR StartCmd\n      SEQINITSTEP Idle",
                ),
            ),
        ),
    ),
    # ---- Tier 3: cross-module / moduletype graph (§6.2) ----
    Probe(
        id="C-101",
        tier=3,
        area="moduletype-graph",
        summary="moduletype instantiation cycle (A instantiates B, B instantiates A)",
        base=None,
        note="user-asserted: loops (moduletype and library) must be found",
        files=(
            ProbeFile(
                "control-acyclic.s",
                "control",
                "accept",
                "TypeA instantiates only a leaf moduletype",
                lambda _: _picture("ModuleChain", _CHAIN_TYPES, _PROBE_TOP_LOCALVARS),
            ),
            ProbeFile(
                "violation-cycle.s",
                "violation",
                "reject",
                "TypeA and TypeB instantiate each other",
                lambda _: _picture("ModuleLoop", _CYCLE_TYPES, _PROBE_TOP_LOCALVARS),
            ),
        ),
    ),
    Probe(
        id="C-102",
        tier=3,
        area="moduletype-graph",
        summary="moduletype instantiates itself (degenerate loop)",
        base=None,
        note="model-derived variant of C-101",
        files=(
            ProbeFile(
                "control-acyclic.s",
                "control",
                "accept",
                "TypeA instantiates only a leaf moduletype",
                lambda _: _picture("ModuleChain", _CHAIN_TYPES, _PROBE_TOP_LOCALVARS),
            ),
            ProbeFile(
                "violation-self-instance.s",
                "violation",
                "reject",
                "TypeA instantiates TypeA",
                lambda _: _picture("ModuleSelfLoop", _SELF_TYPE_A, _PROBE_TOP_LOCALVARS),
            ),
        ),
    ),
    Probe(
        id="C-103",
        tier=3,
        area="moduletype-graph",
        summary="moduletype not invoked anywhere in its declaring unit",
        base="edge_cases:SimpleModuleTypeInvocation",
        note="user example: 'moduletype is not invoked in the library where it is declared'",
        files=(
            ProbeFile(
                "control-instantiated.s", "control", "accept", "PumpType instantiated once (in base)", identity()
            ),
            ProbeFile(
                "violation-unused.s",
                "violation",
                "reject",
                "PumpType declared but never instantiated",
                replace_line(
                    "   SpeedRef: real  := 50.0;\n\nSUBMODULES\n   Pump Invocation\n      ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5\n       ) : PumpType (\n      Speed => SpeedRef);\n\nModuleDef",
                    "   SpeedRef: real  := 50.0;\n\nModuleDef",
                ),
            ),
        ),
    ),
    Probe(
        id="C-104",
        tier=3,
        area="moduletype-graph",
        summary="instance references a moduletype with no definition",
        base="edge_cases:SimpleModuleTypeInvocation",
        note="ModuleTypeInstance is fully skipped in validation today",
        files=(
            ProbeFile(
                "control-defined.s", "control", "accept", "instance binds to a defined moduletype (in base)", identity()
            ),
            ProbeFile(
                "violation-undefined-binding.s",
                "violation",
                "reject",
                "instance binds to an undefined moduletype name",
                replace_line("       ) : PumpType (", "       ) : GhostType ("),
            ),
        ),
    ),
    Probe(
        id="C-105",
        tier=3,
        area="moduletype-graph",
        summary="instance parameter arity vs declared module parameters",
        base="valid:SubmoduleParams",
        note="hypothesis: declaring 3 params and mapping 2 (or 4) is rejected",
        files=(
            ProbeFile(
                "control-full-arity.s", "control", "accept", "all three module parameters mapped (in base)", identity()
            ),
            ProbeFile(
                "violation-missing-mapping.s",
                "violation",
                "reject",
                "Gain mapping omitted from the instance call",
                replace_line(
                    "      Setpoint => GLOBAL GlobalSetpoint,\n      Gain => 2.0,",
                    "      Setpoint => GLOBAL GlobalSetpoint,",
                ),
            ),
        ),
    ),
    Probe(
        id="C-106",
        tier=3,
        area="moduletype-graph",
        summary="parameter transfer type compatibility (boolean mapped into real param)",
        base="valid:SubmoduleParams",
        note="hypothesis: value mapped to a real parameter must itself be numeric",
        files=(
            ProbeFile(
                "control-typed-transfer.s", "control", "accept", "real-to-real parameter mapping (in base)", identity()
            ),
            ProbeFile(
                "violation-bool-to-real.s",
                "violation",
                "reject",
                "boolean variable mapped into a real parameter",
                replace_line("      Setpoint => ProcessSetpoint,", "      Setpoint => ControlEnabled,"),
            ),
        ),
    ),
    # ---- Tier 3: graphics correlation (§6.3) ----
    Probe(
        id="C-201",
        tier=3,
        area="graphics-correlation",
        summary="code/graphics header-date parity",
        base="valid:MinimalProgram",
        note="user-asserted: the dates in the initial header lines must match between code and graphics",
        files=(
            ProbeFile(
                "control-date-match.s",
                "control",
                "accept",
                "graphics .y carries the same first-line date as code .s",
                identity(),
            ),
            ProbeFile(
                "violation-date-shift.s",
                "violation",
                "reject",
                "graphics .y date differs from code .s by one day",
                identity(),
                y="shift-date",
            ),
        ),
    ),
    Probe(
        id="C-202",
        tier=3,
        area="graphics-correlation",
        summary="composite-object count parity between code and graphics",
        base="valid:MinimalProgram",
        note="user-asserted: code and graphics must contain the same number of composite objects",
        files=(
            ProbeFile(
                "control-count-match.s",
                "control",
                "accept",
                "graphics .y declares the same (zero) objects as code",
                identity(),
            ),
            ProbeFile(
                "violation-extra-object.s",
                "violation",
                "reject",
                "graphics .y declares one composite object the code lacks",
                identity(),
                y="extra-object",
            ),
        ),
    ),
)
