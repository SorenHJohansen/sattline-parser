"""AST model definitions and formatting helpers."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any, Literal

from ..names import fold_identifier
from ._ast_model_support import (
    InitValue,
    code_comment_list,
    code_item_list,
    datatype_def_list,
    format_list,
    graph_object_list,
    interact_object_list,
    modulecode_list,
    moduledef_list,
    moduletype_def_list,
    parameter_mapping_list,
    render_base_picture,
    render_frame_module,
    render_module_code,
    render_moduletype_def,
    render_moduletype_instance,
    render_single_module,
    sfc_body_list,
    submodule_list,
    variable_list,
)
from .clauses import ClippingClause, ModuleArguments
from .expressions import (
    Assignment,
    BinOp,
    BoolOp,
    CodeComment,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    SLExpression,
    SLStmt,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from .properties import (
    GraphProperties,
    InteractProperties,
    graph_properties,
    interact_properties,
)
from .tails import Tail, tail_list

__all__ = [
    "Assignment",
    "BasePicture",
    "BinOp",
    "BoolOp",
    "CodeComment",
    "CodeItem",
    "Compare",
    "DataType",
    "Equation",
    "FloatLiteral",
    "FrameModule",
    "FuncCall",
    "FuncCallStmt",
    "GraphObject",
    "GraphicsBinding",
    "IfStmt",
    "IntLiteral",
    "InteractObject",
    "MappingSource",
    "ModuleCode",
    "ModuleDef",
    "ModuleHeader",
    "ModuleTypeDef",
    "ModuleTypeInstance",
    "NotOp",
    "ParameterMapping",
    "SFCAlternative",
    "SFCBodyItem",
    "SFCCodeBlocks",
    "SFCFork",
    "SFCParallel",
    "SFCStep",
    "SFCSubsequence",
    "SFCTransition",
    "SFCTransitionSub",
    "SLExpression",
    "SLStmt",
    "Sequence",
    "Simple_DataType",
    "SingleModule",
    "SourceSpan",
    "TernaryOp",
    "UnaryOp",
    "VarRef",
    "Variable",
]


@dataclass(frozen=True)
class SourceSpan:
    """A source range in the *original* (un-preprocessed) source text.

    ``start`` and ``end`` are zero-based character offsets into the original
    source, with ``end`` exclusive. ``line`` and ``column`` are one-based and
    describe the start of the span (``line`` starting at 1, ``column`` starting
    at 1). All positions refer to the original source even when the text was
    compressed/decoded before parsing (see ``sattline_parser.source_document``).
    """

    start: int
    end: int
    line: int
    column: int

    def __reduce__(self):
        return (type(self), (self.start, self.end, self.line, self.column))


# CodeItem: the element type of Equation.code and SFCCodeBlocks enter/active/exit.
# SFCBodyItem: the element type of Sequence.code (SFC structure nodes + comments).
type CodeItem = Assignment | FuncCallStmt | IfStmt | CodeComment
type SFCBodyItem = (
    SFCStep | SFCTransition | SFCTransitionSub | SFCAlternative | SFCParallel | SFCSubsequence | CodeComment
)


class IntLiteral(int):
    span: SourceSpan | None

    def __new__(cls, value: int, span: SourceSpan | None = None):
        obj = int.__new__(cls, value)
        obj.span = span
        return obj

    def __reduce__(self):
        return (type(self), (int(self), self.span))


class FloatLiteral(float):
    span: SourceSpan | None

    def __new__(cls, value: float, span: SourceSpan | None = None):
        obj = float.__new__(cls, value)
        obj.span = span
        return obj

    def __reduce__(self):
        return (type(self), (float(self), self.span))


class Simple_DataType(Enum):
    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    IDENTSTRING = "identstring"
    TAGSTRING = "tagstring"
    TIME = "time"
    DURATION = "duration"
    LINESTRING = "linestring"
    MAXSTRING = "maxstring"
    REAL = "real"

    @classmethod
    def from_any(cls, value: object) -> Simple_DataType:
        # Use the concrete class in isinstance for proper type narrowing in type checkers.
        if isinstance(value, Simple_DataType):
            return value
        if not isinstance(value, str):
            raise TypeError("Expected Simple_DataType or str")
        # Identifiers fold through the same CP1252 table as every other name in
        # the language, so ``INTEGER``/``Integer``/``integer`` are one datatype.
        folded = fold_identifier(value)
        for member in cls:
            if fold_identifier(member.value) == folded:
                return member
        raise ValueError(f"{value!r} is not a built-in datatype")


@dataclass
class Variable:
    name: str
    datatype: Simple_DataType | str  # accept either at init; we'll normalize
    global_var: bool | None = False
    const: bool | None = False
    state: bool | None = False
    opsave: bool | None = False
    secure: bool | None = False
    init_value: InitValue | None = None
    has_explicit_default: bool = False
    description: str | None = None
    declaration_span: SourceSpan | None = None
    init_is_duration: bool = False
    # Declaration modifiers in SOURCE ORDER, lowercased. The order matters:
    # `State OpSave` loads, while `OpSave State` and `OpSave Const` are invalid
    # attribute mixes. The corpus fixtures `OpSaveAndStateCombined.s` and
    # `OpSaveConstCombined.s` pin the invalid forms, so the flags above cannot
    # express the rule and the order has to be kept.
    attribute_order: tuple[str, ...] = ()

    @property
    def datatype_text(self) -> str:
        # Always return a string representation
        return self.datatype.value if isinstance(self.datatype, Simple_DataType) else str(self.datatype)

    def __post_init__(self):
        # Accept DataType or any-case string
        try:
            self.datatype = Simple_DataType.from_any(self.datatype)
        except ValueError:
            if not isinstance(self.datatype, str):
                raise
            # Keep user-defined datatypes (record names) as strings
            self.datatype = str(self.datatype)

    def __str__(self) -> str:
        return (
            f"Name: {self.name!r}, Datatype: {self.datatype!r}, Global: {self.global_var}, "
            f"Const: {self.const}, State: {self.state}, Init_value : {self.init_value!r}, "
            f"ExplicitDefault: {self.has_explicit_default}, Description: {self.description!r}"
        )


@dataclass
class DataType:
    name: str
    description: str | None
    datecode: int | None
    var_list: list[Variable] = field(default_factory=variable_list)
    origin_file: str | None = None
    origin_lib: str | None = None
    declaration_span: SourceSpan | None = None
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        from ..formatting.formatter import format_list  # noqa: PLC0415

        lines = [
            f"Name       : {self.name!r}",
            f"Description: {self.description!r}",
            f"Datecode   : {self.datecode!r}",
            f"OriginFile : {self.origin_file!r}",
            f"OriginLib  : {self.origin_lib!r}",
            f"Variables in datatype   : {format_list(self.var_list)}",
        ]
        return "Datatype{\n" + textwrap.indent("\n".join(lines), "    ") + "}"


class MappingSource(StrEnum):
    """Where the value of a parameter mapping comes from.

    ``VARIABLE`` is a variable or dotted field reference. ``VALUE`` is a
    literal or a parsed ``Duration_Value``/``Time_Value`` payload.
    """

    VARIABLE = "variable_name"
    VALUE = "value"


@dataclass
class ParameterMapping:
    target: VarRef
    source_type: MappingSource
    is_duration: bool
    is_source_global: bool
    source: VarRef | None = None
    source_literal: InitValue | None = None
    span: SourceSpan | None = None

    def __str__(self) -> str:
        tgt = self.target.name

        if self.is_source_global:
            if self.source is not None:
                return f"{tgt} => GLOBAL {self.source.name}"
            return f"{tgt} => GLOBAL"

        if self.source_type is MappingSource.VARIABLE and self.source:
            return f"{tgt} => {self.source.name}"

        if self.source_literal is not None:
            return f"{tgt} => {self.source_literal!r}"

        return f"{tgt} => <None>"


@dataclass
class GraphObject:
    type: str
    properties: GraphProperties = field(default_factory=graph_properties)
    #: Source span of the object (its ``graph_object`` rule), when positions are
    #: propagated. Graphics correlation uses it to point at the marker.
    span: SourceSpan | None = None


@dataclass
class InteractObject:
    type: str
    properties: InteractProperties = field(default_factory=interact_properties)
    #: Source span of the object rule, when positions are propagated.
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class GraphicsBinding:
    kind: str
    raw_text: str
    value: Any | None = None
    span: SourceSpan | None = None


@dataclass
class ModuleDef:
    #: The ``ClippingBounds`` clause, when the source wrote one. It carries
    #: both the resolved corners and the tails attached to them.
    clipping: ClippingClause | None = None
    zoom_limits: tuple[float, float] | None = None
    seq_layers: float | dict[str, float] | None = None
    grid: float = 0.2
    zoomable: bool = False
    graph_objects: list[GraphObject] = field(default_factory=graph_object_list)
    interact_objects: list[InteractObject] = field(default_factory=interact_object_list)
    #: Source span of the ``ModuleDef`` block, when positions are propagated.
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})

    @property
    def clipping_bounds(self) -> tuple[tuple[float, float], tuple[float, float]] | None:
        """The resolved corner values, or ``None`` when the source omitted them."""
        return self.clipping.bounds if self.clipping is not None else None

    @property
    def clipping_tails(self) -> tuple[Tail, ...] | None:
        """The tails attached to the clipping corners, in source order."""
        return self.clipping.tails if self.clipping is not None else None

    def __str__(self) -> str:
        lines = [
            f"ClippingBounds : {self.clipping_bounds}",
            f"ZoomLimits     : {self.zoom_limits}",
            f"SeqLayers      : {self.seq_layers}",
            f"Grid           : {self.grid}",
            f"Zoomable       : {self.zoomable}",
            # f"GraphObjects   : {format_list(self.graph_objects)}",
            # f"InteractObjects: {format_list(self.interact_objects)}",
        ]
        return "\n" + textwrap.indent("\n".join(lines), "    ")


@dataclass
class Sequence:
    name: str | None
    type: str
    position: tuple[float, float]
    size: tuple[float, float]
    seqcontrol: bool = False
    seqtimer: bool = False
    code: list[SFCBodyItem] = field(default_factory=sfc_body_list)

    def __str__(self) -> str:
        return (
            f"Sequence(name={self.name}, pos={self.position}, "
            f"type={self.type}, control={self.seqcontrol}, timer={self.seqtimer},\n"
            f"    code={format_list(self.code)})"
        )


@dataclass
class Equation:
    """``EQUATIONBLOCK`` / ``EQUATIONS`` body.

    The form accepts the keyword, an optional name, optional coordinate/size
    metadata and layer metadata before ``:``: only the statement list is
    required. ``name``/``position``/``size`` are therefore optional, and
    ``None`` means the source omitted them. ``kind`` records which of the two
    keywords was written; they are kept distinct, and their effect is not
    modelled, so only the spelling is preserved.
    """

    kind: Literal["equationblock", "equations"] = "equationblock"
    name: str | None = None
    position: tuple[float, float] | None = None
    size: tuple[float, float] | None = None
    code: list[CodeItem] = field(default_factory=code_item_list)
    layer_info: int | None = None

    def __str__(self) -> str:
        return f"Equation(name={self.name}, pos={self.position},\n    code={format_list(self.code)})"


@dataclass
class ModuleCode:
    sequences: list[Sequence] | None = None
    equations: list[Equation] | None = None

    def __str__(self) -> str:
        return render_module_code(self)


@dataclass
class ModuleHeader:
    name: str
    invoke_coord: tuple[float, float, float, float, float]
    declaration_span: SourceSpan | None = None
    #: The typed invocation argument list. It is the single source of truth for
    #: the marker, layer, enable, ``Module_In_View``, zoom, and assignment
    #: arguments; the singular fields below are read-only views over it.
    arguments: ModuleArguments = field(default_factory=ModuleArguments)
    #: Only the tails attached to the five ``invoke_coord`` values, in order.
    invoke_coord_tails: list[Tail] = field(default_factory=tail_list)
    groupconn: VarRef | None = None
    groupconn_global: bool = False
    description_comments: list[CodeComment] = field(default_factory=code_comment_list)

    @property
    def invocation_arguments(self) -> tuple[str, ...]:
        """The kinds of the marker arguments, in source order."""
        return tuple(marker.kind for marker in self.arguments.markers)

    @property
    def layer_info(self) -> int | None:
        """The ``Layer_ = <int>`` argument, when the source wrote one."""
        return self.arguments.layer

    @property
    def enable(self) -> bool | None:
        """The ``Enable_`` value, when the source wrote one."""
        enable = self.arguments.enable
        return enable.enabled if enable is not None else None

    @property
    def enable_tail(self) -> Tail | None:
        """The optional tail of the ``Enable_`` argument."""
        enable = self.arguments.enable
        return enable.tail if enable is not None else None

    @property
    def module_in_view(self) -> bool | None:
        """The ``Module_In_View`` value, distinct from ``Enable_``."""
        clause = self.arguments.module_in_view
        return clause.in_view if clause is not None else None

    @property
    def zoom_limits(self) -> tuple[float, float] | None:
        """The ``ZoomLimits`` pair, when the source wrote one."""
        limits = self.arguments.zoom_limits
        return (limits.minimum, limits.maximum) if limits is not None else None

    @property
    def zoomable(self) -> bool:
        """True when the ``Zoomable`` marker argument is present."""
        return self.arguments.zoomable


class _ModuleBlockViews:
    """Read-only singular views over the ``moduledefs``/``modulecodes`` lists.

    The lists are the single source of truth. ``moduledef`` and ``modulecode``
    are derived properties so a consumer reading "the last block" can never
    observe a value that differs from the blocks the transformer stored.
    """

    # Deliberately a plain class: the annotations below only type the property
    # access. Decorating this base with ``@dataclass`` would turn them into
    # duplicate fields and reintroduce the divergence this view prevents.
    moduledefs: list[ModuleDef]
    modulecodes: list[ModuleCode]

    @property
    def moduledef(self) -> ModuleDef | None:
        """The last ``ModuleDef`` block, or ``None`` when the module has none."""
        return self.moduledefs[-1] if self.moduledefs else None

    @property
    def modulecode(self) -> ModuleCode | None:
        """The last ``ModuleCode`` block, or ``None`` when the module has none."""
        return self.modulecodes[-1] if self.modulecodes else None


@dataclass
class SingleModule(_ModuleBlockViews):
    header: ModuleHeader
    datecode: int | None = None
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    #: Every ``ModuleDef`` block from a ``moduledef_block*`` run, in source
    #: order. Legacy coded files repeat one ``ModuleDef ... [ModuleCode ...]
    #: ENDDEF`` block per layer, so a singular field alone cannot represent them
    #: without silently dropping all but the last block.
    moduledefs: list[ModuleDef] = field(default_factory=moduledef_list)
    #: Every ``ModuleCode`` block from a ``moduledef_block*`` run, in source
    #: order. ``modulecode`` is a derived read-only property over this list.
    modulecodes: list[ModuleCode] = field(default_factory=modulecode_list)
    parametermappings: list[ParameterMapping] = field(default_factory=parameter_mapping_list)
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        return render_single_module(self)


@dataclass
class FrameModule(_ModuleBlockViews):
    header: ModuleHeader
    datecode: int | None = None
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    moduledefs: list[ModuleDef] = field(default_factory=moduledef_list)
    modulecodes: list[ModuleCode] = field(default_factory=modulecode_list)
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        return render_frame_module(self)


@dataclass
class ModuleTypeInstance:
    header: ModuleHeader
    moduletype_name: str
    parametermappings: list[ParameterMapping] = field(default_factory=parameter_mapping_list)

    def __str__(self) -> str:
        return render_moduletype_instance(self)


@dataclass
class ModuleTypeDef(_ModuleBlockViews):
    name: str
    datecode: int | None = None
    is_private: bool = False
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    moduledefs: list[ModuleDef] = field(default_factory=moduledef_list)
    modulecodes: list[ModuleCode] = field(default_factory=modulecode_list)
    parametermappings: list[ParameterMapping] = field(default_factory=parameter_mapping_list)
    groupconn: VarRef | None = None
    groupconn_global: bool = False
    origin_file: str | None = None
    origin_lib: str | None = None
    declaration_span: SourceSpan | None = None
    description_comments: list[CodeComment] = field(default_factory=code_comment_list)
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        return render_moduletype_def(self)


@dataclass
class BasePicture(_ModuleBlockViews):
    header: ModuleHeader
    name: str = "BasePicture"
    program_name: str | None = None
    position: tuple[float, float, float, float, float] | None = None
    datatype_defs: list[DataType] = field(default_factory=datatype_def_list)
    moduletype_defs: list[ModuleTypeDef] = field(default_factory=moduletype_def_list)
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    moduledefs: list[ModuleDef] = field(default_factory=moduledef_list)
    modulecodes: list[ModuleCode] = field(default_factory=modulecode_list)
    origin_file: str | None = None
    origin_lib: str | None = None
    graphics_file: str | None = None
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)
    #: Explicit DateCode_ attribute of the root module definition, when present.
    #: Absent is preserved as ``None``; stamping an import date is a separate
    #: operation and must never be faked during parsing.
    datecode: int | None = None
    #: The original Lark parse tree, attached by ``parse_source_text`` /
    #: ``parse_source_file`` only when ``retain_parse_tree=True`` is passed, as a
    #: debugging/tooling convenience. It is deliberately *not* part of the
    #: persistent semantic AST: pickling strips it (see ``__getstate__``) so
    #: cached/serialized payloads stay small and self-contained. Code should not
    #: rely on ``parse_tree`` surviving a pickle round-trip.
    parse_tree: Any | None = None

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        # The Lark tree is parse-result/tooling state, not persistent AST state;
        # dropping it keeps pickled payloads small and avoids accidentally
        # serializing huge trees.
        state["parse_tree"] = None
        return state

    def __str__(self) -> str:
        return render_base_picture(self)


@dataclass
class SFCCodeBlocks:
    enter: list[CodeItem] = field(default_factory=code_item_list)
    active: list[CodeItem] = field(default_factory=code_item_list)
    exit: list[CodeItem] = field(default_factory=code_item_list)


@dataclass
class SFCStep:
    kind: str  # 'init' or 'step'
    name: str | None
    code: SFCCodeBlocks
    #: ``SEQFORK`` suffix attached to this step, if any.
    fork: SFCFork | None = None
    #: Source span of the element, so position diagnostics can point at it.
    span: SourceSpan | None = None


@dataclass
class SFCTransition:
    name: str | None
    #: Guard expression; ``None`` when the source omits ``WAIT_FOR`` entirely.
    #: The omission is accepted and the compiler lowers it to true, so absence
    #: is preserved rather than synthesized.
    condition: SLExpression | None
    #: ``SEQFORK`` suffix attached to this transition, if any.
    fork: SFCFork | None = None
    span: SourceSpan | None = None


@dataclass
class SFCAlternative:
    branches: list[list[SFCBodyItem]]  # each branch is a list of SFC nodes
    span: SourceSpan | None = None


@dataclass
class SFCParallel:
    branches: list[list[SFCBodyItem]]
    span: SourceSpan | None = None


@dataclass
class SFCSubsequence:
    #: ``SUBSEQUENCE`` / ``SUBSEQSTEP`` name; both are optional.
    name: str | None
    body: list[SFCBodyItem]
    #: ``'sequence'`` for ``SUBSEQUENCE`` (structural position M) or
    #: ``'substep'`` for ``SUBSEQSTEP`` (step position S). The two share a model
    #: shape but occupy different positions in a sequence body.
    kind: str = "sequence"
    span: SourceSpan | None = None


@dataclass
class SFCTransitionSub:
    name: str | None
    body: list[SFCBodyItem]
    span: SourceSpan | None = None


@dataclass
class SFCFork:
    """``SEQFORK`` jump list, optionally closed by ``SEQBREAK``.

    The form takes one or more comma-separated target names followed by an
    optional ``SEQBREAK``, and only ever appears as a suffix of a step or a
    transition. A standalone ``SEQBREAK`` is not a sequence element.
    """

    targets: tuple[str, ...]
    has_break: bool = False
