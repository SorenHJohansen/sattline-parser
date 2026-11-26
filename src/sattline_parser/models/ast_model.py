"""AST model definitions and formatting helpers."""

from __future__ import annotations

import dataclasses
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
    graph_object_list,
    interact_object_list,
    moduletype_def_list,
    parameter_mapping_list,
    render_base_picture,
    render_datatype,
    render_equation,
    render_frame_module,
    render_module_code,
    render_moduletype_def,
    render_moduletype_instance,
    render_sequence,
    render_single_module,
    sfc_body_list,
    submodule_list,
    variable_list,
)
from .clauses import ClippingClause, ModuleArguments, NestedClipping
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
from .freeze import FrozenNode
from .header import HeaderInfo
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
    "ScalarDatatype",
    "Sequence",
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
    """An integer literal that keeps its source position and written spelling.

    Equality is the inherited numeric one, so ``IntLiteral(1) == 1`` and
    ``IntLiteral(1) == FloatLiteral(1.0)`` are both true. The written form is
    not part of equality: read ``span``, ``written``, or ``type(value)`` when the
    spelling (``1`` versus ``1.0``) matters.

    ``value`` is the value the model keeps. A literal outside the 32-bit range
    is normalised to the nearest bound, so ``2147483648`` is stored as
    ``2147483647`` with ``clamped=True``; ``written`` still holds the text the
    source wrote, which is what a diagnostic quotes. The normalisation is the
    parser's own, not a claim about what the language stores.
    """

    span: SourceSpan | None
    clamped: bool
    written: str | None

    def __new__(
        cls,
        value: int,
        span: SourceSpan | None = None,
        clamped: bool = False,
        written: str | None = None,
    ):
        obj = int.__new__(cls, value)
        object.__setattr__(obj, "span", span)
        object.__setattr__(obj, "clamped", clamped)
        object.__setattr__(obj, "written", written)
        return obj

    def __setattr__(self, name: str, value: object) -> None:
        raise dataclasses.FrozenInstanceError(f"cannot assign to field {name!r} on a literal")

    def __delattr__(self, name: str) -> None:
        raise dataclasses.FrozenInstanceError(f"cannot delete field {name!r} on a literal")

    def __reduce__(self):
        return (type(self), (int(self), self.span, self.clamped, self.written))


class FloatLiteral(float):
    """A real literal that keeps its source position and written spelling.

    Equality is the inherited numeric one, so ``FloatLiteral(1.0) == 1``. The
    written form is not part of equality; read ``span``, ``written``, or
    ``type(value)`` when it matters. ``written`` keeps the source text of a
    literal that was clamped to the language range, so a diagnostic can quote
    what was written rather than the clamped value.
    """

    span: SourceSpan | None
    clamped: bool
    written: str | None

    def __new__(
        cls,
        value: float,
        span: SourceSpan | None = None,
        clamped: bool = False,
        written: str | None = None,
    ):
        obj = float.__new__(cls, value)
        object.__setattr__(obj, "span", span)
        object.__setattr__(obj, "clamped", clamped)
        object.__setattr__(obj, "written", written)
        return obj

    def __setattr__(self, name: str, value: object) -> None:
        raise dataclasses.FrozenInstanceError(f"cannot assign to field {name!r} on a literal")

    def __delattr__(self, name: str) -> None:
        raise dataclasses.FrozenInstanceError(f"cannot delete field {name!r} on a literal")

    def __reduce__(self):
        return (type(self), (float(self), self.span, self.clamped, self.written))


class ScalarDatatype(Enum):
    """The language's built-in scalar datatypes.

    A recognized datatype name normalizes to a member through :meth:`from_any`
    and :func:`sattline_parser.names.fold_identifier`, so ``INTEGER``,
    ``Integer``, and ``integer`` are one datatype. A user-defined record type
    stays a plain ``str``; the validator resolves its fields through the type
    graph.
    """

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
    def from_any(cls, value: object) -> ScalarDatatype:
        # Use the concrete class in isinstance for proper type narrowing in type checkers.
        if isinstance(value, ScalarDatatype):
            return value
        if not isinstance(value, str):
            raise TypeError("Expected ScalarDatatype or str")
        # Identifiers fold through the same CP1252 table as every other name in
        # the language, so ``INTEGER``/``Integer``/``integer`` are one datatype.
        folded = fold_identifier(value)
        for member in cls:
            if fold_identifier(member.value) == folded:
                return member
        raise ValueError(f"{value!r} is not a built-in datatype")


@dataclass
class Variable(FrozenNode):
    name: str
    datatype: ScalarDatatype | str  # accept either at init; we'll normalize
    global_var: bool | None = False
    const: bool | None = False
    state: bool | None = False
    opsave: bool | None = False
    secure: bool | None = False
    init_value: InitValue | None = None
    has_explicit_default: bool = False
    description: str | None = None
    declaration_span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})
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
        return self.datatype.value if isinstance(self.datatype, ScalarDatatype) else str(self.datatype)

    def __post_init__(self):
        # Accept DataType or any-case string
        try:
            self.datatype = ScalarDatatype.from_any(self.datatype)
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
class DataType(FrozenNode):
    name: str
    description: str | None
    datecode: int | None
    var_list: list[Variable] = field(default_factory=variable_list)
    origin_file: str | None = None
    origin_lib: str | None = None
    declaration_span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        return render_datatype(self)


class MappingSource(StrEnum):
    """Where the value of a parameter mapping comes from.

    ``VARIABLE`` is a variable or dotted field reference. ``VALUE`` is a
    literal or a parsed ``Duration_Value``/``Time_Value`` payload.
    """

    VARIABLE = "variable_name"
    VALUE = "value"


@dataclass
class ParameterMapping(FrozenNode):
    target: VarRef
    source_type: MappingSource
    is_duration: bool
    is_source_global: bool
    source: VarRef | None = None
    source_literal: InitValue | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})

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
class GraphObject(FrozenNode):
    type: str
    properties: GraphProperties = field(default_factory=graph_properties)
    #: Source span of the object (its ``graph_object`` rule), when positions are
    #: propagated. Graphics correlation uses it to point at the marker.
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class InteractObject(FrozenNode):
    #: The interactor keyword exactly as written (``ComBut_``, ``TextBox_``,
    #: ``ComButProc_``, ``ProcedureInteract``, or a free-form name). The
    #: formatter writes this spelling back, so ``ProcedureInteract`` no longer
    #: collapses to ``ComButProc_``.
    type: str
    properties: InteractProperties = field(default_factory=interact_properties)
    #: Source span of the object rule, when positions are propagated.
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})

    @property
    def kind(self) -> str:
        """The written spelling folded through the language identifier table.

        One rule for every interactor: compare ``kind`` when the written case
        does not matter. ``ComButProc_`` and ``ProcedureInteract`` stay distinct
        kinds because the source wrote different keywords and their effect is
        not modelled.
        """
        return fold_identifier(self.type)


@dataclass
class GraphicsBinding(FrozenNode):
    kind: str
    raw_text: str
    value: Any | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class ModuleDef(FrozenNode):
    #: The ``ClippingBounds`` clause, when the source wrote one. It carries
    #: both the resolved corners and the tails attached to them.
    clipping: ClippingClause | None = None
    zoom_limits: tuple[float, float] | None = None
    #: ``Two_Layers_ LayerLimit_ = <real>``. Only a module has layers, and the
    #: value is the zoom level at which it switches from displaying layer 1 to
    #: layer 2. ``None`` means the module has a single layer. Objects carry
    #: their own ``Layer_`` number.
    layer_limit: float | None = None
    #: ``Grid = <real>``. ``None`` means the source wrote no ``Grid`` clause, so
    #: a written ``Grid = 0.2`` is not silently dropped as a default.
    grid: float | None = None
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
            f"LayerLimit     : {self.layer_limit}",
            f"Grid           : {self.grid}",
            f"Zoomable       : {self.zoomable}",
            # f"GraphObjects   : {format_list(self.graph_objects)}",
            # f"InteractObjects: {format_list(self.interact_objects)}",
        ]
        return "\n" + textwrap.indent("\n".join(lines), "    ")


@dataclass
class Sequence(FrozenNode):
    name: str | None
    type: str
    position: tuple[float, float] = field(compare=False, metadata={"layout": True})
    size: tuple[float, float] = field(compare=False, metadata={"layout": True})
    seqcontrol: bool = False
    seqtimer: bool = False
    code: list[SFCBodyItem] = field(default_factory=sfc_body_list)
    #: ``Layer_ = <int>`` written after the ``OBJSIZE`` pair, when present.
    #: Absence is preserved as ``None``, matching ``Equation.layer_info``.
    layer_info: int | None = None
    #: Source span of the sequence declaration, when positions are propagated.
    declaration_span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})

    def __str__(self) -> str:
        return render_sequence(self)


@dataclass
class Equation(FrozenNode):
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
    position: tuple[float, float] | None = field(default=None, compare=False, metadata={"layout": True})
    size: tuple[float, float] | None = field(default=None, compare=False, metadata={"layout": True})
    code: list[CodeItem] = field(default_factory=code_item_list)
    layer_info: int | None = None
    #: Source span of the equation declaration, when positions are propagated.
    declaration_span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})

    def __str__(self) -> str:
        return render_equation(self)


@dataclass
class ModuleCode(FrozenNode):
    sequences: list[Sequence] | None = None
    equationblocks: list[Equation] | None = None

    def __str__(self) -> str:
        return render_module_code(self)


@dataclass
class ModuleHeader(FrozenNode):
    name: str
    invoke_coord: tuple[float, float, float, float, float] = field(compare=False, metadata={"layout": True})
    declaration_span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})
    #: The typed invocation argument list. It is the single source of truth for
    #: the marker, layer, enable, ``Module_In_View``, zoom, and assignment
    #: arguments; the singular fields below are read-only views over it.
    arguments: ModuleArguments = field(default_factory=ModuleArguments)
    #: Only the tails attached to the five ``invoke_coord`` values, in order.
    invoke_coord_tails: list[Tail] = field(default_factory=tail_list)
    groupconn: VarRef | None = None
    groupconn_global: bool = False
    description_comments: list[CodeComment] = field(default_factory=code_comment_list)
    #: The same tails, one group per ``invoke_coord`` value, so a reader can
    #: place each one where it was written. Empty when the header was assembled
    #: without position information. The tails are the same objects as
    #: ``invoke_coord_tails``, never copies.
    coordinate_tails: tuple[tuple[Tail, ...], ...] = ()
    #: Nested ``ClippingBounds`` annotations written after one ``invoke_coord``
    #: value, one group per value in ``invoke_coord`` order. Their tails are part
    #: of ``invoke_coord_tails``, and the annotation keeps the values themselves.
    coordinate_clippings: tuple[tuple[NestedClipping, ...], ...] = ()

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


@dataclass
class SingleModule(FrozenNode):
    header: ModuleHeader
    datecode: int | None = None
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    #: The module body's single layout block. The grammar requires one
    #: ``ModuleDef`` and allows one optional ``ModuleCode``; ``None`` occurs only
    #: on a synthetic view such as an empty picture.
    moduledef: ModuleDef | None = None
    modulecode: ModuleCode | None = None
    parametermappings: list[ParameterMapping] = field(default_factory=parameter_mapping_list)
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        return render_single_module(self)


@dataclass
class FrameModule(FrozenNode):
    header: ModuleHeader
    datecode: int | None = None
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    #: The module body's single layout block. The grammar requires one
    #: ``ModuleDef`` and allows one optional ``ModuleCode``; ``None`` occurs only
    #: on a synthetic view such as an empty picture.
    moduledef: ModuleDef | None = None
    modulecode: ModuleCode | None = None
    #: ``(P => value)`` mappings written after ``ENDDEF``. A frame module takes
    #: the same optional invocation tail as a single module, so the mappings are
    #: kept rather than dropped.
    parametermappings: list[ParameterMapping] = field(default_factory=parameter_mapping_list)
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        return render_frame_module(self)


@dataclass
class ModuleTypeInstance(FrozenNode):
    header: ModuleHeader
    moduletype_name: str
    parametermappings: list[ParameterMapping] = field(default_factory=parameter_mapping_list)

    def __str__(self) -> str:
        return render_moduletype_instance(self)


@dataclass
class ModuleTypeDef(FrozenNode):
    name: str
    datecode: int | None = None
    is_private: bool = False
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    #: The module body's single layout block. The grammar requires one
    #: ``ModuleDef`` and allows one optional ``ModuleCode``; ``None`` occurs only
    #: on a synthetic view such as an empty picture.
    moduledef: ModuleDef | None = None
    modulecode: ModuleCode | None = None
    groupconn: VarRef | None = None
    groupconn_global: bool = False
    origin_file: str | None = None
    origin_lib: str | None = None
    declaration_span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})
    description_comments: list[CodeComment] = field(default_factory=code_comment_list)
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)

    def __str__(self) -> str:
        return render_moduletype_def(self)


@dataclass
class BasePicture(FrozenNode):
    header: ModuleHeader
    name: str = "BasePicture"
    program_name: str | None = None
    #: The three quoted header lines and the optional change description, as
    #: written. ``program_name`` above is the convenience view over it.
    header_info: HeaderInfo | None = None
    position: tuple[float, float, float, float, float] | None = field(
        default=None, compare=False, metadata={"layout": True}
    )
    datatype_defs: list[DataType] = field(default_factory=datatype_def_list)
    moduletype_defs: list[ModuleTypeDef] = field(default_factory=moduletype_def_list)
    moduleparameters: list[Variable] = field(default_factory=variable_list)
    localvariables: list[Variable] = field(default_factory=variable_list)
    submodules: list[SingleModule | FrameModule | ModuleTypeInstance] = field(default_factory=submodule_list)
    #: The module body's single layout block. The grammar requires one
    #: ``ModuleDef`` and allows one optional ``ModuleCode``; ``None`` occurs only
    #: on a synthetic view such as an empty picture.
    moduledef: ModuleDef | None = None
    modulecode: ModuleCode | None = None
    origin_file: str | None = None
    origin_lib: str | None = None
    trailing_comments: list[CodeComment] = field(default_factory=code_comment_list)
    #: Explicit DateCode_ attribute of the root module definition, when present.
    #: Absent is preserved as ``None``; stamping an import date is a separate
    #: operation and must never be faked during parsing.
    datecode: int | None = None
    #: The root module's ``(Frame_Module)`` marker, when the source wrote one.
    #: The marker sits after the datecode on the same definition line, so it is
    #: not an invocation argument.
    is_frame_module: bool = False

    def __str__(self) -> str:
        return render_base_picture(self)


@dataclass
class SFCCodeBlocks(FrozenNode):
    enter: list[CodeItem] = field(default_factory=code_item_list)
    active: list[CodeItem] = field(default_factory=code_item_list)
    exit: list[CodeItem] = field(default_factory=code_item_list)


@dataclass
class SFCStep(FrozenNode):
    kind: str  # 'init' or 'step'
    name: str | None
    code: SFCCodeBlocks
    #: ``SEQFORK`` suffix attached to this step, if any.
    fork: SFCFork | None = None
    #: Source span of the element, so position diagnostics can point at it.
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class SFCTransition(FrozenNode):
    name: str | None
    #: Guard expression; ``None`` when the source omits ``WAIT_FOR`` entirely.
    #: The omission is accepted and the compiler lowers it to true, so absence
    #: is preserved rather than synthesized.
    condition: SLExpression | None
    #: ``SEQFORK`` suffix attached to this transition, if any.
    fork: SFCFork | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class SFCAlternative(FrozenNode):
    branches: list[list[SFCBodyItem]]  # each branch is a list of SFC nodes
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class SFCParallel(FrozenNode):
    branches: list[list[SFCBodyItem]]
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class SFCSubsequence(FrozenNode):
    #: ``SUBSEQUENCE`` / ``SUBSEQSTEP`` name; both are optional.
    name: str | None
    body: list[SFCBodyItem]
    #: ``'sequence'`` for ``SUBSEQUENCE`` (structural position M) or
    #: ``'substep'`` for ``SUBSEQSTEP`` (step position S). The two share a model
    #: shape but occupy different positions in a sequence body.
    kind: str = "sequence"
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class SFCTransitionSub(FrozenNode):
    name: str | None
    body: list[SFCBodyItem]
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass
class SFCFork(FrozenNode):
    """``SEQFORK`` jump list, optionally closed by ``SEQBREAK``.

    The form takes one or more comma-separated target names followed by an
    optional ``SEQBREAK``, and only ever appears as a suffix of a step or a
    transition. A standalone ``SEQBREAK`` is not a sequence element.
    """

    targets: tuple[str, ...]
    has_break: bool = False
