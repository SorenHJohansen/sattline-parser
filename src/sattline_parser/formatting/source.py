"""Render a whole parsed file back to SattLine source.

``format_source`` writes a :class:`~sattline_parser.ast.BasePicture` as
canonical SattLine text that parses back to an equal tree. It is a formatter,
not a lossless printer: the model keeps structure and spelling where the
language cares, not the original whitespace, so the output is normalised.

Every corpus fixture that parses, in ``valid/`` and ``edge_cases/``, round-trips,
including graphics and interactor bodies. The ``invalid/`` fixtures fail strict
validation by design, so they are not part of the round-trip set. A tail is
written after the value it followed, using the positional
views ``ModuleHeader.coordinate_tails``, ``ClippingClause.corner_tails``, and
the graph and interact ``coord_tails`` property key. A nested
``ClippingBounds`` annotation is written after the value it annotated, from the
matching ``coordinate_clippings``, ``corner_clippings``, ``coord_clippings``, or
``x_clippings``/``y_clippings`` view.

Five shapes are refused rather than written somewhere they did not appear:

* a hand-assembled model that carries a tail without its positional grouping;
* a parameter mapping whose source literal is absent;
* a multi-key ``time_value`` payload, whose written keyword is not modelled;
* more than two module-header description comments, because the grammar has one
  position before ``Invocation`` and one after it;
* a plain coordinate tail written after a nested ``ClippingBounds`` annotation,
  because the model keeps the annotation beside the tail order.

The output is display text: it is not guaranteed to be byte-identical to any
particular editor's layout, and it is not a supported interchange format.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeGuard, cast

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    BasePicture,
    CodeItem,
    DataType,
    Equation,
    FloatLiteral,
    FrameModule,
    GraphObject,
    InteractObject,
    IntLiteral,
    ModuleCode,
    ModuleDef,
    ModuleHeader,
    ModuleTypeDef,
    ModuleTypeInstance,
    ParameterMapping,
    ScalarDatatype,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCCodeBlocks,
    SFCFork,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
    SingleModule,
    Variable,
)
from sattline_parser.models.clauses import (
    Alignment,
    AssignClause,
    ClippingClause,
    ColourSpec,
    EnableClause,
    FlagClause,
    ModuleArguments,
    ModuleInViewClause,
    NestedClipping,
    PickButton,
    PolygonPoint,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
)
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    CodeComment,
    Compare,
    FuncCall,
    IfStmt,
    NotOp,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.models.properties import GraphProperties, InteractProperties
from sattline_parser.models.tails import LitStringTail, Tail, VarTail

from .formatter import format_expr

__all__ = ["UnsupportedFormattingError", "format_module", "format_source"]


class UnsupportedFormattingError(ValueError):
    """The model lost an association that the source spelling needs.

    Raised instead of writing a value somewhere it was not written. The
    message names the construct and the missing association.
    """


_DEFAULT_HEADER = (
    '" Syntax version 2.23"',
    '"Original file date: ---"',
    '"Program date: ---"',
)


@dataclass(slots=True)
class _Printer:
    indent: str = "    "
    lines: list[str] = field(default_factory=lambda: [])

    def emit(self, level: int, text: str = "") -> None:
        if text:
            self.lines.append(f"{self.indent * level}{text}")
        else:
            self.lines.append("")

    def emit_block(self, level: int, text: str) -> None:
        """Emit multi-line text, indented one level."""
        for line in text.splitlines():
            if line.strip():
                self.emit(level, line)
            else:
                self.emit(level)

    def emit_verbatim(self, level: int, text: str) -> None:
        """Emit token text whose own line breaks and indentation are significant.

        Only the first line takes the level prefix. A preserved comment keeps
        the continuation lines exactly as the token carried them, so a second
        format pass does not shift them.
        """
        lines = text.splitlines() or [text]
        self.emit(level, lines[0])
        self.lines.extend(lines[1:])

    def render(self) -> str:
        return "\n".join(self.lines).rstrip("\n") + "\n"


def format_source(picture: BasePicture, *, indent: str = "    ") -> str:
    """Render *picture* as canonical SattLine source.

    ``indent`` is one nesting level in the output. The result is intended to be
    parsed again; it round-trips to an equal tree for every construct whose
    model association is complete.

    Raises :class:`UnsupportedFormattingError` when the model cannot say where a
    value belonged, rather than writing it somewhere it was not.
    """
    printer = _Printer(indent=indent)
    for line in _header_lines(picture):
        printer.emit(0, line)
    description = picture.header_info.description if picture.header_info is not None else None
    if description is not None:
        printer.emit(0, description.text)
    datecode = f" DateCode_ {picture.datecode}" if picture.datecode is not None else ""
    frame = " (Frame_Module)" if picture.is_frame_module else ""
    header = _module_header(picture.header)
    printer.emit(0, f"{header} : MODULEDEFINITION{datecode}{frame}")
    _emit_scan_group(printer, picture.header, 0)
    _emit_body(printer, picture, 0)
    printer.emit(0, _enddef_text(picture.trailing_comments))
    return printer.render()


def format_module(module: ModuleDef, *, indent: str = "    ") -> str:
    """Render one ``ModuleDef`` block, without a header or ``ModuleCode``."""
    printer = _Printer(indent=indent)
    _emit_module_def(printer, module, 0)
    return printer.render()


def _header_lines(picture: BasePicture) -> tuple[str, str, str]:
    info = picture.header_info
    if info is None:
        return _DEFAULT_HEADER
    return (
        _quoted_header_line(info.syntax_version_line),
        _quoted_header_line(info.original_file_date_line),
        _quoted_header_line(info.program_date_line),
    )


def _enddef_text(comments: list[CodeComment], *, tail: str = "") -> str:
    """One ``ENDDEF`` line, with the end comment and any invocation tail."""
    trailing = " ".join(comment.text for comment in comments)
    body = f"ENDDEF {trailing}" if trailing else "ENDDEF"
    return f"{body}{tail};"


def _quoted_header_line(text: str) -> str:
    # A header line keeps the text inside its quotes, so a doubled inner quote
    # has to be escaped again when it is written back.
    return _string(text)


def _emit_body(printer: _Printer, picture: BasePicture, level: int) -> None:
    _emit_definitions(printer, picture.datatype_defs, picture.moduletype_defs, level)
    _emit_variables(printer, const.GRAMMAR_VALUE_MODULEPARAMETERS, picture.moduleparameters, level)
    _emit_variables(printer, const.GRAMMAR_VALUE_LOCALVARIABLES, picture.localvariables, level)
    if picture.submodules:
        printer.emit(level, const.GRAMMAR_VALUE_SUBMODULES)
        for submodule in picture.submodules:
            _emit_submodule(printer, submodule, level + 1)
    if picture.moduledef is not None:
        _emit_module_def(printer, picture.moduledef, level)
    if picture.modulecode is not None:
        _emit_module_code(printer, picture.modulecode, level)


def _emit_scan_group(printer: _Printer, header: ModuleHeader, level: int) -> None:
    text = _scan_group_text(header)
    if text:
        printer.emit(level, text)


def _scan_group_text(header: ModuleHeader) -> str:
    if header.groupconn is None:
        return ""
    global_keyword = "GLOBAL " if header.groupconn_global else ""
    return f" (GroupConn = {global_keyword}{format_expr(header.groupconn)})"


def _emit_definitions(
    printer: _Printer,
    datatypes: list[DataType],
    moduletypes: list[ModuleTypeDef],
    level: int,
) -> None:
    if datatypes:
        printer.emit(level, const.GRAMMAR_VALUE_TYPEDEFINITIONS)
        for datatype in datatypes:
            _emit_datatype(printer, datatype, level + 1)
    if moduletypes:
        printer.emit(level, const.GRAMMAR_VALUE_TYPEDEFINITIONS)
        for moduletype in moduletypes:
            _emit_moduletype(printer, moduletype, level + 1)


def _emit_datatype(printer: _Printer, datatype: DataType, level: int) -> None:
    # An empty written description is a description, not an absent one.
    description = f" {_string(datatype.description)}" if datatype.description is not None else ""
    datecode = f" DateCode_ {datatype.datecode}" if datatype.datecode is not None else ""
    printer.emit(level, f"{datatype.name}{description} = RECORD{datecode}")
    _emit_variable_groups(printer, datatype.var_list, level + 1)
    printer.emit(level, _enddef_text(datatype.trailing_comments))


def _emit_moduletype(printer: _Printer, moduletype: ModuleTypeDef, level: int) -> None:
    description_comments = "".join(f" {comment.text}" for comment in moduletype.description_comments)
    private = "PRIVATE_ " if moduletype.is_private else ""
    datecode = f" DateCode_ {moduletype.datecode}" if moduletype.datecode is not None else ""
    groupconn = ""
    if moduletype.groupconn is not None:
        global_keyword = "GLOBAL " if moduletype.groupconn_global else ""
        groupconn = f" (GroupConn = {global_keyword}{format_expr(moduletype.groupconn)})"
    printer.emit(level, f"{moduletype.name}{description_comments} = {private}MODULEDEFINITION{datecode}{groupconn}")
    _emit_variables(printer, const.GRAMMAR_VALUE_MODULEPARAMETERS, moduletype.moduleparameters, level + 1)
    _emit_variables(printer, const.GRAMMAR_VALUE_LOCALVARIABLES, moduletype.localvariables, level + 1)
    if moduletype.submodules:
        printer.emit(level + 1, const.GRAMMAR_VALUE_SUBMODULES)
        for submodule in moduletype.submodules:
            _emit_submodule(printer, submodule, level + 2)
    if moduletype.moduledef is not None:
        _emit_module_def(printer, moduletype.moduledef, level + 1)
    if moduletype.modulecode is not None:
        _emit_module_code(printer, moduletype.modulecode, level + 1)
    printer.emit(level, _enddef_text(moduletype.trailing_comments))


def _emit_variables(printer: _Printer, keyword: str, variables: list[Variable], level: int) -> None:
    if not variables:
        return
    printer.emit(level, keyword)
    _emit_variable_groups(printer, variables, level + 1)


def _emit_variable_groups(printer: _Printer, variables: list[Variable], level: int) -> None:
    for group in _group_variables(variables):
        printer.emit(level, _variable_group_text(group))


def _group_variables(variables: list[Variable]) -> list[list[Variable]]:
    """Group adjacent variables that share a datatype and modifiers.

    The source writes ``A, B: integer`` for one declaration; the model holds one
    ``Variable`` per name. Regrouping restores the written shape without
    changing any declaration's meaning.
    """
    groups: list[list[Variable]] = []
    for variable in variables:
        if groups:
            previous = groups[-1][0]
            if _same_declaration(previous, variable) and not variable.description:
                groups[-1].append(variable)
                continue
        groups.append([variable])
    return groups


def _same_declaration(left: Variable, right: Variable) -> bool:
    return (
        left.datatype == right.datatype
        and left.global_var == right.global_var
        and left.const == right.const
        and left.state == right.state
        and left.opsave == right.opsave
        and left.secure == right.secure
        and left.init_value == right.init_value
        and left.has_explicit_default == right.has_explicit_default
        and left.init_is_duration == right.init_is_duration
        and left.attribute_order == right.attribute_order
    )


def _variable_group_text(group: list[Variable]) -> str:
    items = ", ".join(_variable_item_text(variable) for variable in group)
    first = group[0]
    global_keyword = "GLOBAL " if first.global_var else ""
    datatype = _datatype_text(first.datatype)
    modifiers = "".join(f" {keyword}" for keyword in _modifier_keywords(first))
    initial = (
        ""
        if first.init_value is None and not first.has_explicit_default and not first.init_is_duration
        else f" := {_init_value_text(first)}"
    )
    return f"{items}: {global_keyword}{datatype}{modifiers}{initial};"


def _variable_item_text(variable: Variable) -> str:
    if variable.description is None:
        return variable.name
    return f"{variable.name} {_string(variable.description)}"


def _modifier_keywords(variable: Variable) -> tuple[str, ...]:
    declared = {
        "const": (variable.const, "CONST"),
        "state": (variable.state, "STATE"),
        "opsave": (variable.opsave, "OPSAVE"),
        "secure": (variable.secure, "SECURE"),
    }
    ordered = list(variable.attribute_order) or ["const", "state", "opsave", "secure"]
    return tuple(keyword for name in ordered if (entry := declared.get(name)) and entry[0] for keyword in [entry[1]])


def _init_value_text(variable: Variable) -> str:
    if variable.has_explicit_default:
        return "DEFAULT"
    value = variable.init_value
    if variable.init_is_duration:
        if isinstance(value, str):
            return f"{const.GRAMMAR_VALUE_DURATION_VALUE} {_string(value)}"
        if value is None:
            # A bare ``Duration_Value`` initializer has no payload text; the
            # marker alone is the initializer.
            return const.GRAMMAR_VALUE_DURATION_VALUE
        return str(value)
    if isinstance(value, Mapping):
        return _time_value_text(value)
    return _value_text(value)


def _time_value_text(payload: Mapping[str, str | None]) -> str:
    """Render a parsed ``Time_Value`` payload as the source spelling."""
    if len(payload) != 1:
        raise UnsupportedFormattingError("a multi-key time_value payload cannot be rendered from its parsed dict")
    ((keyword, text),) = payload.items()
    if text is None:
        return keyword
    return f"{keyword} {_string(text)}"


def _datatype_text(datatype: ScalarDatatype | str) -> str:
    if isinstance(datatype, ScalarDatatype):
        return datatype.value
    return datatype


def _emit_submodule(printer: _Printer, submodule: SingleModule | FrameModule | ModuleTypeInstance, level: int) -> None:
    if isinstance(submodule, ModuleTypeInstance):
        header = _module_header(submodule.header)
        mappings = ", ".join(_mapping_text(mapping) for mapping in submodule.parametermappings)
        tail = f" ({mappings})" if mappings else ""
        printer.emit(level, f"{header} : {submodule.moduletype_name}{tail};")
        return
    header = _module_header(submodule.header)
    frame = " (Frame_Module)" if isinstance(submodule, FrameModule) else ""
    datecode = f" DateCode_ {submodule.datecode}" if submodule.datecode is not None else ""
    scan_group = _scan_group_text(submodule.header)
    printer.emit(level, f"{header} : MODULEDEFINITION{datecode}{frame}{scan_group}")
    _emit_variables(printer, const.GRAMMAR_VALUE_MODULEPARAMETERS, submodule.moduleparameters, level + 1)
    _emit_variables(printer, const.GRAMMAR_VALUE_LOCALVARIABLES, submodule.localvariables, level + 1)
    if submodule.submodules:
        printer.emit(level + 1, const.GRAMMAR_VALUE_SUBMODULES)
        for nested in submodule.submodules:
            _emit_submodule(printer, nested, level + 2)
    if submodule.moduledef is not None:
        _emit_module_def(printer, submodule.moduledef, level + 1)
    if submodule.modulecode is not None:
        _emit_module_code(printer, submodule.modulecode, level + 1)
    mappings = ", ".join(_mapping_text(mapping) for mapping in submodule.parametermappings)
    tail = f" ({mappings})" if mappings else ""
    printer.emit(level, _enddef_text(submodule.trailing_comments, tail=tail))


def _emit_module_def(printer: _Printer, module: ModuleDef, level: int) -> None:
    printer.emit(level, const.GRAMMAR_VALUE_MODULEDEF)
    clipping = module.clipping
    if clipping is not None:
        _emit_clipping(printer, clipping, level)
    if module.layer_limit is not None:
        printer.emit(level, f"Two_Layers_ LayerLimit_ = {_real(module.layer_limit)}")
    if module.zoom_limits is not None:
        printer.emit(level, f"ZoomLimits = {_real(module.zoom_limits[0])} {_real(module.zoom_limits[1])}")
    if module.zoomable:
        printer.emit(level, "Zoomable")
    if module.grid is not None:
        printer.emit(level, f"Grid = {_real(module.grid)}")
    if module.graph_objects:
        printer.emit(level, f"{const.GRAMMAR_VALUE_GRAPHOBJECTS} :")
        for graph_object in module.graph_objects:
            _emit_graph_object(printer, graph_object, level + 1)
    if module.interact_objects:
        printer.emit(level, f"{const.GRAMMAR_VALUE_INTERACTOBJECTS} :")
        for interact_object in module.interact_objects:
            _emit_interact_object(printer, interact_object, level + 1)


def _emit_clipping(printer: _Printer, clipping: ClippingClause, level: int) -> None:
    (x1, y1), (x2, y2) = clipping.bounds
    values = (x1, y1, x2, y2)
    groups = clipping.corner_tails
    grouped = {id(tail) for group in groups for tail in group}
    if any(id(tail) not in grouped for tail in clipping.tails):
        raise UnsupportedFormattingError(
            "clipping tails: this clause carries tails without their corners, "
            "so the corner each tail belonged to is not known"
        )
    rendered = [
        _coordinate_value_text(
            value, _tail_group_at(groups, index), _clipping_group_at(clipping.corner_clippings, index)
        )
        for index, value in enumerate(values)
    ]
    printer.emit(level, f"ClippingBounds = ( {rendered[0]} , {rendered[1]} ) ( {rendered[2]} , {rendered[3]} )")


def _module_header(header: ModuleHeader) -> str:
    groups = header.coordinate_tails
    grouped = {id(tail) for group in groups for tail in group}
    if any(id(tail) not in grouped for tail in header.invoke_coord_tails):
        raise UnsupportedFormattingError(
            "module header coordinate tails: this header carries tails without their "
            "coordinates, so the coordinate each tail belonged to is not known"
        )
    coordinames = ", ".join(
        _coordinate_value_text(
            value, _tail_group_at(groups, index), _clipping_group_at(header.coordinate_clippings, index)
        )
        for index, value in enumerate(header.invoke_coord)
    )
    arguments = _arguments_text(header.arguments)
    inner = f"( {coordinames}" + (f" {arguments}" if arguments else "") + " )"
    # The grammar has one description-comment position before ``Invocation`` and
    # one after it. The model keeps them in one ordered list, so the first one
    # goes back to the first position and the second to the second; writing both
    # before ``Invocation`` produced source the grammar rejects.
    comments = header.description_comments
    if len(comments) > 2:
        raise UnsupportedFormattingError(
            "module header description comments: the grammar has one comment position "
            "before Invocation and one after it"
        )
    before = "".join(f" {comment.text}" for comment in comments[:1])
    after = "".join(f" {comment.text}" for comment in comments[1:])
    return f"{header.name}{before} Invocation{after} {inner}"


def _arguments_text(arguments: ModuleArguments) -> str:
    parts: list[str] = []
    if arguments.layer is not None:
        parts.append(f"Layer_ = {arguments.layer}")
    if arguments.enable is not None:
        parts.append(_enable_text(arguments.enable, parenthesised=True))
    if arguments.module_in_view is not None:
        parts.append(_module_in_view_text(arguments.module_in_view))
    if arguments.zoom_limits is not None:
        limits = arguments.zoom_limits
        parts.append(f"ZoomLimits = {_real(limits.minimum)} {_real(limits.maximum)}")
    if arguments.zoomable:
        parts.append("Zoomable")
    for marker in arguments.markers:
        parts.append(marker.kind)
    for assignment in arguments.assigns:
        parts.append(_assign_text(assignment))
    return " ".join(parts)


def _enable_text(clause: EnableClause, *, parenthesised: bool) -> str:
    text = f"Enable_ = {_bool(clause.enabled)}"
    if clause.tail is not None:
        text += _tail_text(clause.tail, parenthesised=parenthesised)
    return text


def _module_in_view_text(clause: ModuleInViewClause) -> str:
    text = f"Module_In_View = {_bool(clause.in_view)}"
    if clause.tail is not None:
        text += _tail_text(clause.tail, parenthesised=False)
    return text


def _assign_text(clause: AssignClause) -> str:
    text = f"{clause.name} = {_expression_text(clause.value)}"
    if clause.tail is not None:
        text += _tail_text(clause.tail, parenthesised=True)
    return text


def _emit_module_code(printer: _Printer, modulecode: ModuleCode, level: int) -> None:
    printer.emit(level, const.GRAMMAR_VALUE_MODULECODE)
    for sequence in modulecode.sequences or ():
        _emit_sequence(printer, sequence, level)
    for equation in modulecode.equationblocks or ():
        _emit_equation(printer, equation, level)


def _emit_equation(printer: _Printer, equation: Equation, level: int) -> None:
    keyword = "EQUATIONBLOCK" if equation.kind == "equationblock" else "EQUATIONS"
    name = f" {equation.name}" if equation.name else ""
    coord = f" COORD {_real(equation.position[0])}, {_real(equation.position[1])}" if equation.position else ""
    size = f" OBJSIZE {_real(equation.size[0])}, {_real(equation.size[1])}" if equation.size else ""
    layer = f" {_layer_text(equation.layer_info)}" if equation.layer_info is not None else ""
    printer.emit(level, f"{keyword}{name}{coord}{size}{layer} :")
    _emit_code_items(printer, equation.code, level + 1)


def _layer_text(layer: int) -> str:
    return f"Layer_ = {layer}"


def _emit_sequence(printer: _Printer, sequence: Sequence, level: int) -> None:
    keyword = "SEQUENCE" if sequence.type == "SEQUENCE" else "OPENSEQUENCE"
    name = f" {sequence.name}" if sequence.name else ""
    control = ""
    flags = [
        flag for flag, enabled in (("SEQCONTROL", sequence.seqcontrol), ("SEQTIMER", sequence.seqtimer)) if enabled
    ]
    if flags:
        control = f" ({', '.join(flags)})"
    coord = f" COORD {_real(sequence.position[0])}, {_real(sequence.position[1])}"
    size = f" OBJSIZE {_real(sequence.size[0])}, {_real(sequence.size[1])}"
    layer = f" {_layer_text(sequence.layer_info)}" if sequence.layer_info is not None else ""
    printer.emit(level, f"{keyword}{name}{control}{coord}{size}{layer}")
    _emit_sfc_body(printer, sequence.code, level + 1)
    printer.emit(level, "ENDSEQUENCE" if sequence.type == "SEQUENCE" else "ENDOPENSEQUENCE")


def _emit_sfc_body(printer: _Printer, body: list[SFCBodyItem], level: int) -> None:
    for item in body:
        _emit_sfc_item(printer, item, level)


def _emit_sfc_item(printer: _Printer, item: SFCBodyItem, level: int) -> None:
    if isinstance(item, CodeComment):
        printer.emit(level, item.text)
    elif isinstance(item, SFCStep):
        keyword = "SEQINITSTEP" if item.kind == "init" else "SEQSTEP"
        name = f" {item.name}" if item.name else ""
        printer.emit(level, f"{keyword}{name}{_fork_text(item.fork)}")
        _emit_code_blocks(printer, item.code, level + 1)
    elif isinstance(item, SFCTransition):
        name = f" {item.name}" if item.name else ""
        guard = f" WAIT_FOR {_expression_text(item.condition)}" if item.condition is not None else ""
        printer.emit(level, f"SEQTRANSITION{name}{guard}{_fork_text(item.fork)}")
    elif isinstance(item, SFCTransitionSub):
        name = f" {item.name}" if item.name else ""
        printer.emit(level, f"SUBSEQTRANSITION{name}")
        _emit_sfc_body(printer, item.body, level + 1)
        printer.emit(level, "ENDSUBSEQTRANSITION")
    elif isinstance(item, SFCSubsequence):
        if item.kind == "substep":
            name = f" {item.name}" if item.name else ""
            printer.emit(level, f"SUBSEQSTEP{name}")
            _emit_sfc_body(printer, item.body, level + 1)
            printer.emit(level, "ENDSUBSEQSTEP")
        else:
            name = f" {item.name}" if item.name else ""
            printer.emit(level, f"SUBSEQUENCE{name}")
            _emit_sfc_body(printer, item.body, level + 1)
            printer.emit(level, "ENDSUBSEQUENCE")
    elif isinstance(item, SFCAlternative):
        printer.emit(level, "ALTERNATIVESEQ")
        for index, branch in enumerate(item.branches):
            if index:
                printer.emit(level, "ALTERNATIVEBRANCH")
            _emit_sfc_body(printer, branch, level + 1)
        printer.emit(level, "ENDALTERNATIVE")
    else:
        printer.emit(level, "PARALLELSEQ")
        for index, branch in enumerate(item.branches):
            if index:
                printer.emit(level, "PARALLELBRANCH")
            _emit_sfc_body(printer, branch, level + 1)
        printer.emit(level, "ENDPARALLEL")


def _fork_text(fork: SFCFork | None) -> str:
    if fork is None:
        return ""
    targets = ", ".join(fork.targets)
    return f" SEQFORK {targets}" + (" SEQBREAK" if fork.has_break else "")


def _emit_code_blocks(printer: _Printer, blocks: SFCCodeBlocks, level: int) -> None:
    for keyword, items in (
        ("ENTERCODE", blocks.enter),
        ("ACTIVECODE", blocks.active),
        ("EXITCODE", blocks.exit),
    ):
        if items:
            printer.emit(level, keyword)
            _emit_code_items(printer, items, level + 1)


def _emit_code_items(printer: _Printer, items: list[CodeItem], level: int) -> None:
    for item in items:
        _emit_code_item(printer, item, level)


def _emit_code_item(printer: _Printer, item: CodeItem, level: int) -> None:
    text = format_expr(item, indent=printer.indent)
    if isinstance(item, CodeComment):
        # The comment's own line breaks and indentation are part of the token,
        # so re-indenting each line would change the preserved text.
        printer.emit_verbatim(level, text)
        return
    printer.emit_block(level, text)


def _emit_graph_object(printer: _Printer, graph_object: GraphObject, level: int) -> None:
    properties = graph_object.properties
    kind = graph_object.type
    if kind == const.GRAMMAR_VALUE_COMPOSITEOBJECT:
        text = const.GRAMMAR_VALUE_COMPOSITEOBJECT
        if const.KEY_LAYER in properties:
            text += f" {_layer_text(properties[const.KEY_LAYER])}"
        printer.emit(level, text)
        return
    if kind == const.GRAMMAR_VALUE_CONNECTIONNODE and const.KEY_COORDS not in properties:
        printer.emit(level, const.GRAMMAR_VALUE_CONNECTIONNODE)
        return

    flat_tails = tuple(properties.get(const.KEY_TAILS, ()))
    tail_order = {id(tail): index for index, tail in enumerate(flat_tails)}
    used: set[int] = set()
    head = _graph_head(properties, kind, used)
    items_free = _graph_free_items(properties)
    items_tailed = _graph_tailed_items(properties, tail_order)
    for _order, _text, tails in items_tailed:
        for tail in tails:
            used.add(id(tail))
    common = _graph_common_pieces(properties, tail_order)
    for _text, tails in common:
        for tail in tails:
            used.add(id(tail))
    if kind == const.GRAMMAR_VALUE_TEXTOBJECT and items_free == [] and items_tailed == []:
        # A text object's bare label text is not modelled, but the grammar needs
        # one item before the common properties. An empty string parses back to
        # the same tree because no field records a bare text content.
        items_free.append(_string(""))
    if any(id(tail) not in used for tail in flat_tails):
        raise UnsupportedFormattingError(
            f"{kind}: a tail is not attached to a modelled coordinate or clause, "
            "so it cannot be written where it was written"
        )
    item_texts = [text for _order, text, _tails in sorted(items_tailed, key=lambda piece: piece[0])]
    common_texts = [text for text, _tails in common]
    if const.KEY_LAYER in properties:
        common_texts.insert(0, _layer_text(properties[const.KEY_LAYER]))
    parts = (*head, *items_free, *item_texts, *common_texts)
    printer.emit(level, " ".join(part for part in parts if part))


def _graph_head(properties: GraphProperties, kind: str, used: set[int]) -> list[str]:
    """The object keyword, its polygon type, and its coordinates with tails."""
    head: list[str] = [kind]
    if kind == const.GRAMMAR_VALUE_POLYGONOBJECT:
        head.extend(properties.get(const.KEY_POLYGON_TYPE, ()))
    groups = properties.get(const.KEY_COORD_TAILS, ())
    clippings = properties.get(const.KEY_COORD_CLIPPINGS, ())
    coords = properties.get(const.KEY_COORDS)
    if coords is not None:
        if kind == const.GRAMMAR_VALUE_SEGMENTOBJECT:
            head.append(_tailed_coords_text(coords, groups, clippings, 0))
            _mark_groups(used, groups, 0, 4)
        else:
            head.append(_tailed_coords_text(coords, groups, clippings, 0))
            _mark_groups(used, groups, 0, len(groups))
    for point in properties.get(const.KEY_POINTS, ()):  # PolygonObject
        head.append(_polygon_point_text(point))
        for tail in (*point.x_tails, *point.y_tails):
            used.add(id(tail))
    if kind == const.GRAMMAR_VALUE_SEGMENTOBJECT and const.KEY_SEGMENT_POINT in properties:
        head.append(_tailed_coords_text(properties[const.KEY_SEGMENT_POINT], groups, clippings, 4))
        _mark_groups(used, groups, 4, 6)
    return head


def _graph_free_items(properties: GraphProperties) -> list[str]:
    """A text object's own pieces that carry no tail.

    The grammar puts these before the shared common properties, so they stay
    apart from the common pieces and are emitted first.
    """
    items: list[str] = []
    for text_var in properties.get(const.KEY_TEXT_VARS, ()):
        items.append(f"{_string(text_var.name)} VarName")
    for alignment in properties.get(const.KEY_ALIGNMENTS, ()):
        items.append(_alignment_text(alignment))
    # Only a text object's positioned ``ConnectionNode (x, y)`` clause belongs
    # in the clause run. The bare marker the shared common properties allow is
    # written with the common pieces instead, because the clause run has no bare
    # form.
    connection_node = properties.get(const.KEY_CONNECTION_NODE)
    if connection_node is not None and const.KEY_COORDS in connection_node.properties:
        items.append(_connection_node_text(connection_node))
    for key in (const.KEY_VALUE_FRACTION, const.KEY_WIDTH, const.KEY_FORMAT_STRING):
        clause = properties.get(key)
        if clause is not None and clause.tail is None:
            items.append(_tailed_clause_text(clause))
    return items


def _graph_tailed_items(
    properties: GraphProperties,
    tail_order: dict[int, int],
) -> list[tuple[int, str, tuple[Tail, ...]]]:
    """A text object's tailed clauses, each with its position in the tail list."""
    items: list[tuple[int, str, tuple[Tail, ...]]] = []
    for key in (const.KEY_VALUE_FRACTION, const.KEY_WIDTH, const.KEY_FORMAT_STRING):
        clause = properties.get(key)
        if clause is None or clause.tail is None:
            continue
        items.append((_tail_order(tail_order, clause.tail), _tailed_clause_text(clause), (clause.tail,)))
    return items


def _graph_common_pieces(
    properties: GraphProperties,
    tail_order: dict[int, int],
) -> list[tuple[str, tuple[Tail, ...]]]:
    """The shared common properties in source order: ``Enable_`` and colours.

    The colour blocks keep their list order, because the model stores them in
    written order and their order is part of the tree. A tailed ``Enable_`` is
    placed relative to the tailed colours by its position in the flat tail list,
    so the written tail order survives the round trip. An untailed clause has no
    position of its own and keeps the model order.
    """
    colours = [(_colour_text(colour), _colour_tails(colour)) for colour in properties.get(const.KEY_COLOURS, ())]
    pieces = list(colours)
    enable = _enable_clause(properties)
    if enable is not None:
        text = _enable_text(enable, parenthesised=True)
        if enable.tail is None:
            pieces = [(text, ()), *colours]
        else:
            position = _tail_order(tail_order, enable.tail)
            index = next(
                (
                    index
                    for index, (_text, tails) in enumerate(colours)
                    if tails and _tail_order(tail_order, tails[0]) > position
                ),
                len(colours),
            )
            pieces = [*colours[:index], (text, (enable.tail,)), *colours[index:]]
    # A bare ``ConnectionNode`` marker has no tail and no modelled position
    # inside the common run, so it is written last.
    connection_node = properties.get(const.KEY_CONNECTION_NODE)
    if connection_node is not None and const.KEY_COORDS not in connection_node.properties:
        pieces.append((_connection_node_text(connection_node), ()))
    return pieces


def _mark_groups(used: set[int], groups: tuple[tuple[Tail, ...], ...], start: int, stop: int) -> None:
    for group in groups[start:stop]:
        for tail in group:
            used.add(id(tail))


def _tail_order(tail_order: dict[int, int], tail: Tail) -> int:
    return tail_order.get(id(tail), len(tail_order))


def _enable_clause(properties: GraphProperties) -> EnableClause | None:
    if const.KEY_ENABLE not in properties:
        return None
    tail = properties.get(const.KEY_ENABLE_TAIL)
    return EnableClause(enabled=properties[const.KEY_ENABLE], tail=tail)


def _colour_tails(colour: ColourSpec) -> tuple[Tail, ...]:
    tails: list[Tail] = []
    if colour.width is not None and colour.width.tail is not None:
        tails.append(colour.width.tail)
    for assignment in colour.assignments:
        if assignment.tail is not None:
            tails.append(assignment.tail)
    if colour.style is not None and colour.style.tail is not None:
        tails.append(colour.style.tail)
    return tuple(tails)


def _tailed_coords_text(
    coords: object,
    groups: tuple[tuple[Tail, ...], ...],
    clippings: tuple[tuple[NestedClipping, ...], ...],
    offset: int,
) -> str:
    """Render one pair or box, placing each value's tails after that value."""
    if _is_pair(coords):
        return (
            f"( {_coordinate_text(coords[0], groups, clippings, offset)} , "
            f"{_coordinate_text(coords[1], groups, clippings, offset + 1)} )"
        )
    if isinstance(coords, tuple):
        box = cast("tuple[object, object]", coords)
        if len(box) == 2:
            first = cast("tuple[object, object]", box[0])
            second = cast("tuple[object, object]", box[1])
            return (
                f"( {_coordinate_text(first[0], groups, clippings, offset)} , "
                f"{_coordinate_text(first[1], groups, clippings, offset + 1)} ) "
                f"( {_coordinate_text(second[0], groups, clippings, offset + 2)} , "
                f"{_coordinate_text(second[1], groups, clippings, offset + 3)} )"
            )
    raise UnsupportedFormattingError(f"unexpected coordinate shape: {coords!r}")


def _coordinate_text(
    value: object,
    groups: tuple[tuple[Tail, ...], ...],
    clippings: tuple[tuple[NestedClipping, ...], ...],
    index: int,
) -> str:
    """One coordinate value at a known position in its run."""
    return _coordinate_value_text(value, _tail_group_at(groups, index), _clipping_group_at(clippings, index))


def _emit_interact_object(printer: _Printer, interact_object: InteractObject, level: int) -> None:
    properties = interact_object.properties
    flat_tails = tuple(properties.get(const.KEY_TAILS, ()))
    tail_order = {id(tail): index for index, tail in enumerate(flat_tails)}
    used: set[int] = set()
    parts = [interact_object.type]
    groups = properties.get(const.KEY_COORD_TAILS, ())
    clippings = properties.get(const.KEY_COORD_CLIPPINGS, ())
    offset = 0
    for coords in properties.get(const.KEY_COORDS) or ():
        parts.append(_tailed_coords_text(coords, groups, clippings, offset))
        offset += 4 if not _is_pair(coords) else 2
    for tail in (tail for group in groups for tail in group):
        used.add(id(tail))
    procedure = properties.get(const.KEY_PROCEDURE)
    if procedure is not None:
        parts.append(_procedure_text(procedure))
    printer.emit(level, " ".join(parts))
    for layer in properties.get(const.KEY_LAYERS, ()):
        printer.emit(level + 1, _layer_text(layer))
    body = properties.get(const.KEY_BODY)
    if body is not None:
        lines = [(_interact_body_text(entry), _entry_tails(entry)) for entry in body]
    else:
        lines = _interact_clause_lines(properties, tail_order)
    for text, tails in lines:
        for tail in tails:
            used.add(id(tail))
        printer.emit(level + 1, text)
    if any(id(tail) not in used for tail in flat_tails):
        raise UnsupportedFormattingError(
            f"{interact_object.type}: a tail is not attached to a modelled clause, "
            "so it cannot be written where it was written"
        )


def _interact_clause_lines(
    properties: InteractProperties,
    tail_order: dict[int, int],
) -> list[tuple[str, tuple[Tail, ...]]]:
    """The flat-list clauses of a ``ComButProc_``, in source order.

    Each kind is one list, and its own order is part of the model. The kinds are
    merged by each clause's first tail position in the flat tail list, which is
    the source order, while a clause without a tail keeps its place behind the
    previous clause of the same kind. If the two orders disagree the model lost
    the interleaving, so the formatter refuses instead of guessing.
    """
    sequences: list[list[tuple[str, tuple[Tail, ...]]]] = []
    assigns = [
        (_assign_text(clause), (clause.tail,) if clause.tail is not None else ())
        for clause in properties.get(const.KEY_ASSIGNS, ())
    ]
    enables = [
        (_enable_text(clause, parenthesised=False), (clause.tail,) if clause.tail is not None else ())
        for clause in properties.get(const.KEY_ENABLES, ())
    ]
    flags = [
        (_interact_body_text(clause), (clause.tail,) if clause.tail is not None else ())
        for clause in properties.get(const.KEY_FLAGS, ())
    ]
    colours = [(_colour_text(colour), _colour_tails(colour)) for colour in properties.get(const.KEY_COLOURS, ())]
    for sequence in (assigns, enables, flags, colours):
        if sequence:
            sequences.append(sequence)
    positions = [0] * len(sequences)
    merged: list[tuple[str, tuple[Tail, ...]]] = []
    last = -1
    remaining = sum(len(sequence) for sequence in sequences)
    while remaining:
        choice: int | None = None
        choice_key = 0
        for index, sequence in enumerate(sequences):
            if positions[index] >= len(sequence):
                continue
            text, tails = sequence[positions[index]]
            del text
            key = _tail_order(tail_order, tails[0]) if tails else last
            if choice is None or key < choice_key:
                choice, choice_key = index, key
        if choice is None:  # pragma: no cover - remaining > 0 guarantees a candidate
            break
        if choice_key < last:
            raise UnsupportedFormattingError(
                "interactor clauses: their per-kind order and their written order disagree, "
                "so the source interleaving is not known"
            )
        text, tails = sequences[choice][positions[choice]]
        merged.append((text, tails))
        positions[choice] += 1
        remaining -= 1
        last = choice_key
    return merged


def _entry_tails(entry: object) -> tuple[Tail, ...]:
    """The tails an interactor body entry owns."""
    if isinstance(entry, TailedClause | AssignClause | EnableClause | FlagClause):
        return (entry.tail,) if entry.tail is not None else ()
    if isinstance(entry, ColourSpec):
        return _colour_tails(entry)
    if isinstance(entry, VarTail | LitStringTail | VarRef | BinOp | BoolOp | Compare | NotOp | TernaryOp | UnaryOp):
        return (entry,)
    return ()


def _procedure_text(procedure: ProcedureCall) -> str:
    if not procedure.args:
        return procedure.name
    parts = [procedure.name]
    for argument in procedure.args:
        text = _tail_arg_text(argument)
        parts.append(text if text.startswith(" ") else f" {text}")
    return "".join(parts)


def _tail_arg_text(value: object) -> str:
    if isinstance(value, (VarTail, LitStringTail)):
        return _tail_text(value, parenthesised=True)
    if isinstance(value, (bool, int, float, str)):
        return _value_text(value)
    return _tail_text(value, parenthesised=True)


def _interact_body_text(entry: object) -> str:
    # ``layer_info`` is a plain int. A literal integer body value is an
    # ``IntLiteral``, which is an int subclass, so the exact type is what
    # separates the two.
    if type(entry) is int:
        return _layer_text(entry)
    if isinstance(entry, (bool, int, float, str)):
        return _value_text(entry)
    if isinstance(entry, CodeComment):
        return entry.text
    if isinstance(entry, Alignment):
        return _alignment_text(entry)
    if isinstance(entry, AssignClause):
        return _assign_text(entry)
    if isinstance(entry, ColourSpec):
        return _colour_text(entry)
    if isinstance(entry, EnableClause):
        return _enable_text(entry, parenthesised=False)
    if isinstance(entry, FlagClause):
        return entry.name + ("" if entry.tail is None else _tail_text(entry.tail, parenthesised=False))
    if isinstance(entry, PickButton):
        reference = f" {const.GRAMMAR_VALUE_VARNAME}" if entry.reference is not None else ""
        return f"{const.GRAMMAR_VALUE_INTOBJPICKBUTTON} = {_string(entry.value)}{reference}"
    if isinstance(entry, ScaleSelector):
        return const.GRAMMAR_VALUE_RELATIVE if entry.mode == "relative" else const.GRAMMAR_VALUE_ABS
    if isinstance(entry, TailedClause):
        return _tailed_clause_text(entry)
    return _tail_text(entry, parenthesised=True)


def _colour_text(colour: ColourSpec) -> str:
    keyword = "OutlineColour" if colour.kind == "outline" else "FillColour"
    parts = [f"{keyword} :"]
    if colour.width is not None:
        parts.append(_tailed_clause_text(colour.width))
    parts.extend(_tailed_clause_text(assignment) for assignment in colour.assignments)
    if colour.style is not None:
        parts.append(_tailed_clause_text(colour.style))
    return " ".join(parts)


def _alignment_text(alignment: Alignment) -> str:
    return {
        "left": const.GRAMMAR_VALUE_LEFTALIGNED,
        "center": const.GRAMMAR_VALUE_CENTERALIGNED,
        "right": const.GRAMMAR_VALUE_RIGHTALIGNED,
    }[alignment.value]


def _tailed_clause_text(clause: TailedClause) -> str:
    text = f"{clause.key} = {_value_or_expression_text(clause.value)}"
    if clause.tail is not None:
        text += _tail_text(clause.tail, parenthesised=True)
    return text


def _is_pair(coords: object) -> TypeGuard[tuple[object, object]]:
    if not isinstance(coords, tuple):
        return False
    pair = cast("tuple[object, object]", coords)
    return len(pair) == 2 and all(isinstance(item, (int, float)) for item in pair)


def _as_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise UnsupportedFormattingError(f"expected a coordinate number, got {value!r}")


def _polygon_point_text(point: PolygonPoint) -> str:
    x = _coordinate_value_text(point.x, point.x_tails, point.x_clippings)
    y = _coordinate_value_text(point.y, point.y_tails, point.y_clippings)
    return f"( {x} , {y} )"


def _connection_node_text(node: GraphObject) -> str:
    coords = node.properties.get(const.KEY_COORDS)
    if coords is None or not _is_pair(coords):
        return const.GRAMMAR_VALUE_CONNECTIONNODE
    return f"{const.GRAMMAR_VALUE_CONNECTIONNODE} ( {_real(_as_float(coords[0]))} , {_real(_as_float(coords[1]))} )"


def _mapping_text(mapping: ParameterMapping) -> str:
    global_keyword = "GLOBAL " if mapping.is_source_global else ""
    duration_keyword = "Duration_Value " if mapping.is_duration else ""
    prefix = f"{format_expr(mapping.target)} => {global_keyword}{duration_keyword}"
    if mapping.source is not None:
        return f"{prefix}{format_expr(mapping.source)}"
    literal = mapping.source_literal
    if literal is None:
        raise UnsupportedFormattingError(
            f"mapping {mapping.target.name!r}: the model kept no source literal, "
            "so a written falsy literal cannot be reproduced"
        )
    if isinstance(literal, Mapping):
        # A ``Time_Value`` payload is a parsed mapping, not a Python literal: it
        # has to be written back as the keyword and its optional time string.
        return f"{prefix}{_time_value_text(literal)}"
    return f"{prefix}{_value_text(literal)}"


def _tail_group_at(groups: tuple[tuple[Tail, ...], ...], index: int) -> tuple[Tail, ...]:
    """One coordinate tail group, or an empty group when the model records none."""
    return groups[index] if index < len(groups) else ()


def _clipping_group_at(
    groups: tuple[tuple[NestedClipping, ...], ...],
    index: int,
) -> tuple[NestedClipping, ...]:
    """One nested clipping group, or an empty group when it records none."""
    return groups[index] if index < len(groups) else ()


def _coordinate_value_text(
    value: object,
    tails: tuple[Tail, ...],
    clippings: tuple[NestedClipping, ...],
) -> str:
    """One coordinate number, the tails after it, and any nested clipping.

    A nested ``ClippingBounds`` annotation owns the tails of its own values, and
    those same tail objects are part of the coordinate's flat tail group. The
    annotation is written after the plain tails, so the tails it owns are skipped
    here and rendered inside the annotation instead.
    """
    if not clippings:
        return _real(_as_float(value)) + "".join(_tail_text(tail, parenthesised=False) for tail in tails)
    owned = {
        id(clipping_value.tail)
        for clipping in clippings
        for clipping_value in clipping.values
        if clipping_value.tail is not None
    }
    _ensure_clipping_suffix(tails, owned)
    plain = "".join(_tail_text(tail, parenthesised=False) for tail in tails if id(tail) not in owned)
    return _real(_as_float(value)) + plain + "".join(_nested_clipping_text(clipping) for clipping in clippings)


def _ensure_clipping_suffix(tails: tuple[Tail, ...], owned: set[int]) -> None:
    """Refuse a tail written after a nested clipping annotation.

    The model keeps the annotation beside the coordinate's tails rather than
    inside their order, so the only order it can write back is "plain tails,
    then the annotation". A source that wrote a plain tail after the annotation
    is therefore not reconstructible, and the formatter refuses instead of
    reordering the coordinate.
    """
    seen_annotation = False
    for tail in tails:
        if id(tail) in owned:
            seen_annotation = True
        elif seen_annotation:
            raise UnsupportedFormattingError(
                "nested ClippingBounds: a plain coordinate tail was written after the "
                "annotation, so the written order of the coordinate is not known"
            )


def _nested_clipping_text(clipping: NestedClipping) -> str:
    """One nested ``ClippingBounds = <values>`` annotation and its values."""
    values = " ".join(
        _real(clipping_value.value)
        + ("" if clipping_value.tail is None else _tail_text(clipping_value.tail, parenthesised=False))
        for clipping_value in clipping.values
    )
    return f" {const.GRAMMAR_VALUE_CLIPPINGBOUNDS} = {values}"


def _tail_text(tail: object, *, parenthesised: bool) -> str:
    if isinstance(tail, VarTail):
        direction = const.GRAMMAR_VALUE_INVAR_PREFIX if tail.direction == "in" else const.GRAMMAR_VALUE_OUTVAR_PREFIX
        value = tail.value
        if isinstance(value, LitStringTail):
            return f" : {direction} LitString {_string(value.text)}"
        return f" : {direction} {_value_text(value)}"
    if isinstance(tail, LitStringTail):
        return f" : LitString {_string(tail.text)}"
    del parenthesised
    return f" : ({_expression_text(tail)})"


def _expression_text(value: object) -> str:
    if isinstance(value, (VarRef, BinOp, BoolOp, Compare, FuncCall, NotOp, TernaryOp, UnaryOp, Assignment, IfStmt)):
        return format_expr(value).replace("\n", " ")
    return _value_text(value)


def _value_or_expression_text(value: object) -> str:
    if isinstance(value, (bool, int, float, str)):
        return _value_text(value)
    return _expression_text(value)


def _value_text(value: object) -> str:
    if value is None:
        return "0"
    if isinstance(value, bool):
        return _bool(value)
    if isinstance(value, IntLiteral):
        return str(int(value))
    if isinstance(value, FloatLiteral):
        return _real(float(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _real(value)
    if isinstance(value, str):
        return _string(value)
    return str(value)


def _bool(value: bool) -> str:
    return "True" if value else "False"


def _real(value: float) -> str:
    text = repr(float(value))
    return text if "." in text or "e" in text.lower() else f"{text}.0"


def _string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
