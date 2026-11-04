"""Graphics and interact mixin for SLTransformer.

Handles graphics object construction, coordinate handling, interact object building,
and layout specification.
"""

from __future__ import annotations

from typing import Any, Literal, TypeGuard, cast

from lark import Token, Tree

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import GraphObject, InteractObject
from sattline_parser.models.clauses import (
    AssignClause,
    ColourSpec,
    CommonProperties,
    CoordBox,
    CoordPair,
    EnableClause,
    FlagClause,
    ModuleInViewClause,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
)
from sattline_parser.models.expressions import SLExpression
from sattline_parser.models.properties import GraphProperties, InteractBodyEntry, InteractProperties
from sattline_parser.models.tails import Tail

from ._comments_mixin import is_comment_tree
from ._module_shared import InterimCoords, meta_span, v_args

TransformerItem = object
TransformerTree = Tree[object]


def _is_coord_pair(value: object) -> TypeGuard[CoordPair]:
    if not isinstance(value, tuple):
        return False
    pair = cast(tuple[object, ...], value)
    return len(pair) == 2 and all(isinstance(item, int | float) and not isinstance(item, bool) for item in pair)


def _is_coord_box(value: object) -> TypeGuard[CoordBox]:
    if not isinstance(value, tuple):
        return False
    coords = cast(tuple[object, ...], value)
    return len(coords) == 2 and all(_is_coord_pair(item) for item in coords)


def _as_float(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    raise ValueError(f"Expected a numeric coordinate value; got {type(value).__name__}")


def _tree_children(tree: object) -> list[object]:
    return cast(list[object], cast(Tree[object], tree).children)


def _coords_value(coords: object) -> CoordPair | CoordBox:
    return cast(CoordPair | CoordBox, coords)


def _tails_of(node: object) -> list[Tail]:
    """Collect every tail carried by a clause, coordinate, or nested tree."""
    if isinstance(node, TailedClause | EnableClause | ModuleInViewClause | AssignClause | FlagClause):
        return [node.tail] if node.tail is not None else []
    if isinstance(node, ColourSpec | CommonProperties):
        return list(node.tails)
    if isinstance(node, InterimCoords):
        return list(node.tails or ())
    if isinstance(node, Tree):
        tails: list[Tail] = []
        for child in _tree_children(cast(Tree[object], node)):
            tails.extend(_tails_of(child))
        return tails
    if isinstance(node, list):
        tails = []
        for child in cast(list[object], node):
            tails.extend(_tails_of(child))
        return tails
    return []


def _box_coords(items: list[TransformerItem]) -> CoordBox | None:
    for item in items:
        if isinstance(item, InterimCoords) and _is_coord_box(item.coords):
            return item.coords
    return None


def _text_of(node: object) -> str:
    if isinstance(node, str):
        return node
    raise ValueError(f"_extract_text_from_node expected a str or a 'text_content' node; got {type(node).__name__}")


class _GraphicsInteractMixin:
    """Mixin providing graphics and interact object transformation methods."""

    def polygon_type(self, items: list[TransformerItem]) -> list[str]:
        """Grammar polygon_type -> list of polygon type strings (Polyline, Spline, Connection)."""
        return [str(item) for item in items if isinstance(item, Token)]

    def common_properties(self, items: list[TransformerItem]) -> CommonProperties:
        """Grammar common_properties -> layer/enable/colour content.

        ``connection_node_bare`` markers are position-only and carry no property
        payload, so they are skipped rather than merged.
        """
        layer: int | None = None
        enable: EnableClause | None = None
        colours: list[ColourSpec] = []
        for item in items:
            if is_comment_tree(item) or isinstance(item, GraphObject):
                continue
            if isinstance(item, int) and not isinstance(item, bool):
                layer = item
            elif isinstance(item, EnableClause):
                enable = item
            elif isinstance(item, ColourSpec):
                colours.append(item)
        return CommonProperties(layer=layer, enable=enable, colours=tuple(colours))

    @staticmethod
    def _apply_common_properties(properties: GraphProperties, items: list[TransformerItem]) -> None:
        for item in items:
            if not isinstance(item, CommonProperties):
                continue
            if item.layer is not None:
                properties[const.KEY_LAYER] = item.layer
            if item.enable is not None:
                properties[const.KEY_ENABLE] = item.enable.enabled
            if item.colours:
                properties[const.KEY_COLOURS] = list(item.colours)

    def _tailed_clause(self, items: list[TransformerItem]) -> TailedClause:
        """Build the typed ``Keyword = value [tail]`` clause a rule produced."""
        key: str | None = None
        value: SLExpression | None = None
        tail: Tail | None = None
        for item in items:
            if isinstance(item, Token):
                if key is None:
                    key = str(item)
                continue
            if value is None:
                value = cast(SLExpression, item)
            else:
                tail = cast(Tail, item)
        if key is None or value is None:
            raise ValueError(f"tailed clause expected a keyword and a value; got: {items!r}")
        return TailedClause(key=key, value=value, tail=tail)

    @staticmethod
    def _single_clause(items: list[TransformerItem]) -> TailedClause:
        for item in items:
            if isinstance(item, TailedClause):
                return item
        raise ValueError(f"expected a tailed clause; got: {items!r}")

    def format_string_tailed(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar format_string_tailed -> the format string clause and its tail."""
        return self._tailed_clause(items)

    def format_string_plain(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar format_string_plain -> the format string clause without a tail."""
        return self._tailed_clause(items)

    def format_string(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar format_string -> pass through the typed clause."""
        return self._single_clause(items)

    def value_fraction_tailed(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar value_fraction_tailed -> the fraction clause and its tail."""
        return self._tailed_clause(items)

    def value_fraction_plain(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar value_fraction_plain -> the fraction clause without a tail."""
        return self._tailed_clause(items)

    def value_fraction(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar value_fraction -> pass through the typed clause."""
        return self._single_clause(items)

    def width_tailed(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar width_tailed -> the width clause and its tail."""
        return self._tailed_clause(items)

    def width_plain(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar width_plain -> the width clause without a tail."""
        return self._tailed_clause(items)

    def width(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar width -> pass through the typed clause."""
        return self._single_clause(items)

    def assign_colour_tailed(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar assign_colour_tailed -> the colour assignment and its tail."""
        return self._tailed_clause(items)

    def assign_colour_plain(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar assign_colour_plain -> the colour assignment without a tail."""
        return self._tailed_clause(items)

    def assign_colour(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar assign_colour -> pass through the typed clause."""
        return self._single_clause(items)

    def colour_style_tailed(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar colour_style_tailed -> the style clause and its tail."""
        return self._tailed_clause(items)

    def colour_style_plain(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar colour_style_plain -> the style clause without a tail."""
        return self._tailed_clause(items)

    def colour_style(self, items: list[TransformerItem]) -> TailedClause:
        """Grammar colour_style -> pass through the typed clause."""
        return self._single_clause(items)

    def colour_assignments(self, items: list[TransformerItem]) -> tuple[TailedClause, ...]:
        """Grammar colour_assignments -> every colour assignment in order."""
        return tuple(item for item in items if isinstance(item, TailedClause))

    def _colour_spec(self, kind: Literal["outline", "fill"], items: list[TransformerItem]) -> ColourSpec:
        width: TailedClause | None = None
        assignments: tuple[TailedClause, ...] = ()
        style: TailedClause | None = None
        for item in items:
            if isinstance(item, TailedClause):
                if item.key == const.GRAMMAR_VALUE_WIDTH_KEY:
                    width = item
                elif item.key == const.GRAMMAR_VALUE_COLOURSTYLE:
                    style = item
            elif isinstance(item, tuple):
                assignments = cast(tuple[TailedClause, ...], item)
        return ColourSpec(kind=kind, width=width, assignments=assignments, style=style)

    def outline_colour(self, items: list[TransformerItem]) -> ColourSpec:
        """Grammar outline_colour -> the typed outline colour block."""
        return self._colour_spec("outline", items)

    def fill_colour(self, items: list[TransformerItem]) -> ColourSpec:
        """Grammar fill_colour -> the typed fill colour block."""
        return self._colour_spec("fill", items)

    def color_properties(self, items: list[TransformerItem]) -> ColourSpec:
        """Grammar color_properties -> pass through the single colour block."""
        for item in items:
            if isinstance(item, ColourSpec):
                return item
        raise ValueError(f"color_properties expected a colour block; got: {items!r}")

    def _box_graph_object(self, object_type: str, items: list[TransformerItem]) -> GraphObject:
        go = GraphObject(object_type)
        box = _box_coords(items)
        if box is not None:
            go.properties[const.KEY_COORDS] = box
        tails = _tails_of(items)
        if tails:
            go.properties[const.KEY_TAILS] = tails
        self._apply_common_properties(go.properties, items)
        return go

    def _text_vars(self, items: list[TransformerItem]) -> list[str]:
        text_vars: list[str] = []
        for index, item in enumerate(items):
            if not (isinstance(item, Token) and item.type == const.TOKEN_VARNAME):
                continue
            previous = index - 1
            while previous >= 0:
                candidate = items[previous]
                if is_comment_tree(candidate):
                    previous -= 1
                    continue
                text = _text_of(candidate)
                if text:
                    text_vars.append(text)
                    break
                previous -= 1
        return text_vars

    def text_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar text_object -> GraphObject (TEXTOBJECT with text and coordinates)."""
        go = GraphObject(const.GRAMMAR_VALUE_TEXTOBJECT)
        box = _box_coords(items)
        if box is not None:
            go.properties[const.KEY_COORDS] = box
        tails = _tails_of(items)
        if tails:
            go.properties[const.KEY_TAILS] = tails
        self._apply_common_properties(go.properties, items)
        text_vars = self._text_vars(items)
        if text_vars:
            go.properties[const.KEY_TEXT_VARS] = text_vars
        return go

    def text_content(self, items: list[TransformerItem]) -> str:
        """Grammar text_content -> string (unwrap TEXT content)."""
        for it in items:
            if isinstance(it, str):
                return it
        types = ", ".join(type(x).__name__ for x in items)
        raise ValueError(f"text_content expected a str; got: {types}")

    def rectangle_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar rectangle_object -> GraphObject (RECTANGLEOBJECT)."""
        return self._box_graph_object(const.GRAMMAR_VALUE_RECTANGLEOBJECT, items)

    def line_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar line_object -> GraphObject (LINEOBJECT)."""
        return self._box_graph_object(const.GRAMMAR_VALUE_LINEOBJECT, items)

    def oval_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar oval_object -> GraphObject (OVALOBJECT)."""
        return self._box_graph_object(const.GRAMMAR_VALUE_OVALOBJECT, items)

    def polygon_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar polygon_object -> GraphObject (POLYGONOBJECT)."""
        go = GraphObject(const.GRAMMAR_VALUE_POLYGONOBJECT)
        for it in items:
            if isinstance(it, list) and all(isinstance(x, str) for x in cast(list[object], it)):
                go.properties[const.KEY_POLYGON_TYPE] = cast(list[str], it)
                break
        tails = _tails_of(items)
        if tails:
            go.properties[const.KEY_TAILS] = tails
        self._apply_common_properties(go.properties, items)
        return go

    def segment_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar segment_object -> GraphObject (SEGMENTOBJECT)."""
        go = GraphObject(const.GRAMMAR_VALUE_SEGMENTOBJECT)
        for item in items:
            if not isinstance(item, InterimCoords):
                continue
            if _is_coord_box(item.coords):
                go.properties[const.KEY_COORDS] = item.coords
            elif _is_coord_pair(item.coords) and const.KEY_SEGMENT_POINT not in go.properties:
                go.properties[const.KEY_SEGMENT_POINT] = item.coords
        tails = _tails_of(items)
        if tails:
            go.properties[const.KEY_TAILS] = tails
        self._apply_common_properties(go.properties, items)
        return go

    def composite_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar composite_object -> GraphObject (COMPOSITEOBJECT).

        The marker takes only the layer clause (``Layer_ = <int>``); the layer is
        stored under the same key ``common_properties`` uses for other objects.
        """
        go = GraphObject(const.GRAMMAR_VALUE_COMPOSITEOBJECT)
        for it in items:
            if isinstance(it, int) and not isinstance(it, bool):
                go.properties[const.KEY_LAYER] = it
        return go

    def connection_node(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar connection_node -> positioned ConnectionNode graph object."""
        values = [float(item) for item in items if isinstance(item, int | float) and not isinstance(item, bool)]
        if len(values) < 2:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"connection_node expected two REAL coordinates; got: {types}")
        go = GraphObject(const.GRAMMAR_VALUE_CONNECTIONNODE)
        go.properties[const.KEY_COORDS] = (values[0], values[1])
        return go

    def connection_node_bare(self, _items: list[TransformerItem]) -> GraphObject:
        """Grammar connection_node_bare -> standalone ConnectionNode object."""
        return GraphObject(const.GRAMMAR_VALUE_CONNECTIONNODE)

    @v_args(meta=True)
    def graph_object(self, meta: Any, items: list[TransformerItem]) -> GraphObject:
        """Grammar graph_object -> GraphObject with optional layer and its span."""
        obj: GraphObject | None = None
        layer: int | None = None
        for it in items:
            if isinstance(it, GraphObject) and obj is None:
                obj = it
            elif isinstance(it, int) and not isinstance(it, bool):
                layer = it

        if obj is None:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"graph_object expected a GraphObject in items; got: {types}")

        if layer is not None:
            obj.properties[const.KEY_LAYER] = layer
        obj.span = meta_span(meta)
        return obj

    def graph_objects(self, items: list[TransformerItem]) -> list[GraphObject]:
        """Grammar graph_objects -> list of GraphObjects.

        A section-level ``Layer_ = N`` applies to every object in the section
        (the grammar allows at most one ``layer_info`` per ``GraphObjects``
        section), so it is propagated onto objects that do not declare their
        own explicit layer rather than being silently dropped.
        """
        section_layer = next((it for it in items if isinstance(it, int) and not isinstance(it, bool)), None)
        objects = [it for it in items if isinstance(it, GraphObject)]
        if section_layer is not None:
            for obj in objects:
                if const.KEY_LAYER not in obj.properties:
                    obj.properties[const.KEY_LAYER] = section_layer
        return objects

    def interact_objects(self, items: list[TransformerItem]) -> list[InteractObject]:
        """Grammar interact_objects -> list of InteractObjects."""
        out: list[InteractObject] = []
        for it in items:
            if isinstance(it, InteractObject):
                out.append(it)
            elif isinstance(it, Tree):
                for child in _tree_children(cast(Tree[object], it)):
                    if isinstance(child, InteractObject):
                        out.append(child)
        return out

    def combutproc_tail(self, items: list[TransformerItem]) -> TransformerItem:
        """Grammar combutproc_tail -> pass through the single tail item.

        Without this unwrap, every tail would stay a raw ``combutproc_tail``
        Tree and the assignment/flag/enable/layer content would be silently lost.
        """
        for item in items:
            return item
        raise ValueError("combutproc_tail expected a tail item; got no items")

    def combutproc_item(self, items: list[TransformerItem]) -> InteractObject:
        """Grammar combutproc_item -> InteractObject (COMBUTPROC with coordinates and procedure)."""
        coords: list[CoordPair | CoordBox] = []
        procedure: ProcedureCall | None = None
        layers: list[int] = []
        assigns: list[AssignClause] = []
        enables: list[EnableClause] = []
        flags: list[FlagClause] = []
        colours: list[ColourSpec] = []
        for item in items:
            if isinstance(item, InterimCoords):
                coords.append(_coords_value(item.coords))
            elif isinstance(item, ProcedureCall):
                procedure = item
            elif isinstance(item, int) and not isinstance(item, bool):
                layers.append(item)
            elif isinstance(item, AssignClause):
                assigns.append(item)
            elif isinstance(item, EnableClause):
                enables.append(item)
            elif isinstance(item, FlagClause):
                flags.append(item)
            elif isinstance(item, ColourSpec):
                colours.append(item)

        properties: InteractProperties = {const.KEY_COORDS: coords or None}
        if procedure is not None:
            properties[const.KEY_PROCEDURE] = procedure
        if layers:
            properties[const.KEY_LAYERS] = layers
        if assigns:
            properties[const.KEY_ASSIGNS] = assigns
        if enables:
            properties[const.KEY_ENABLES] = enables
        if flags:
            properties[const.KEY_FLAGS] = flags
        if colours:
            properties[const.KEY_COLOURS] = colours
        tails = _tails_of(items)
        if tails:
            properties[const.KEY_TAILS] = tails
        return InteractObject(type=const.GRAMMAR_VALUE_COMBUTPROC, properties=properties)

    def procedure_args(self, items: list[TransformerItem]) -> list[Tail]:
        """Grammar procedure_args -> one procedure argument per ``proc_atom``."""
        return [cast(Tail, item) for item in items if not isinstance(item, Token)]

    def procedure_call(self, items: list[TransformerItem]) -> ProcedureCall:
        """Grammar procedure_call -> procedure name and its argument list."""
        name: str | None = None
        args: list[Tail] = []
        for it in items:
            if name is None and isinstance(it, str):
                name = str(it)
            elif isinstance(it, list):
                args.extend(cast(list[Tail], it))
            else:
                args.append(cast(Tail, it))
        if name is None:
            raise ValueError(f"procedure_call missing name; got: {items!r}")
        return ProcedureCall(name=name, args=tuple(args))

    def _enable_clause(self, items: list[TransformerItem]) -> EnableClause:
        enabled = True
        tail: Tail | None = None
        for item in items:
            if isinstance(item, Token):
                continue
            if isinstance(item, bool):
                enabled = item
            else:
                tail = cast(Tail, item)
        return EnableClause(enabled=enabled, tail=tail)

    def enable(self, items: list[TransformerItem]) -> EnableClause:
        """Grammar enable -> ENABLE_PREFIX '=' BOOL (invar | enable_expression)?

        The tail is optional: `Enable_ = True` is legal on a graph object. When
        present it is either an InVar_/OutVar_ tail or a parenthesised
        expression, the latter written by the compressor as
        `Enable_ = True : ( NOT EnableVar)`.
        """
        return self._enable_clause(items)

    def enable_interact(self, items: list[TransformerItem]) -> EnableClause:
        """Grammar enable_interact -> ENABLE_PREFIX '=' BOOL invar.

        Interact objects require the InVar_/OutVar_ tail and reject a
        parenthesised one with AliasSym Expected, which is why this is a
        separate rule from `enable`.
        """
        return self._enable_clause(items)

    def enable_combut(self, items: list[TransformerItem]) -> EnableClause:
        """Grammar enable_combut -> ENABLE_PREFIX '=' BOOL enable_expression."""
        return self._enable_clause(items)

    def module_in_view(self, items: list[TransformerItem]) -> ModuleInViewClause:
        """Grammar module_in_view -> MODULE_IN_VIEW_KW '=' BOOL [tail].

        The value accepts True/False only and is stored in a field of its own:
        Module_In_View and Enable_ are distinct properties.
        """
        in_view = False
        tail: Tail | None = None
        for item in items:
            if isinstance(item, Token):
                continue
            if isinstance(item, bool):
                in_view = item
            else:
                tail = cast(Tail, item)
        return ModuleInViewClause(in_view=in_view, tail=tail)

    def enable_expression(self, items: list[TransformerItem]) -> Tail:
        """Grammar enable_expression -> expression within enable context."""
        for it in items:
            if not isinstance(it, Token):
                return cast(Tail, it)
        raise ValueError(f"enable_expression expected an expression child; got: {items}")

    def interact_type_simple(self, items: list[TransformerItem]) -> str:
        """Grammar interact_type_simple -> the interactor type name."""
        for item in items:
            if isinstance(item, Token):
                return str(item)
        raise ValueError(f"interact_type_simple expected an interactor token; got: {items!r}")

    def interact_simple_item(self, items: list[TransformerItem]) -> InteractObject:
        """Grammar interact_simple_item -> InteractObject (button, checkbox, textbox, etc.)."""
        itype: str | None = None
        coords: list[CoordPair | CoordBox] = []
        body: list[InteractBodyEntry] = []
        for index, item in enumerate(items):
            if index == 0 and isinstance(item, str):
                itype = item
            elif isinstance(item, InterimCoords):
                coords.append(_coords_value(item.coords))
            elif isinstance(item, Tree) and item.data == const.TREE_TAG_INTERACT_BODY_SEQ:
                body.extend(cast(list[InteractBodyEntry], _tree_children(cast(Tree[object], item))))
        if itype is None:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"interact_simple_item expected an interactor type token; got: {types}")
        properties: InteractProperties = {
            const.KEY_COORDS: coords or None,
            const.KEY_BODY: body or None,
        }
        tails = _tails_of(items)
        if tails:
            properties[const.KEY_TAILS] = tails
        return InteractObject(type=itype, properties=properties)

    def _assign_clause(self, items: list[TransformerItem]) -> AssignClause:
        name: str | None = None
        value: SLExpression | None = None
        tail: Tail | None = None
        for item in items:
            if name is None and isinstance(item, str):
                name = str(item)
            elif value is None:
                value = cast(SLExpression, item)
            else:
                tail = cast(Tail, item)
        if name is None or value is None:
            raise ValueError(f"interact assignment expected a name and a value; got: {items!r}")
        return AssignClause(name=name, value=value, tail=tail)

    def interact_assign_variable_tailed(self, items: list[TransformerItem]) -> AssignClause:
        """Grammar interact_assign_variable_tailed -> variable assignment with tail."""
        return self._assign_clause(items)

    def interact_assign_variable_plain(self, items: list[TransformerItem]) -> AssignClause:
        """Grammar interact_assign_variable_plain -> variable assignment without tail."""
        return self._assign_clause(items)

    def interact_assign_variable(self, items: list[TransformerItem]) -> AssignClause:
        """Grammar interact_assign_variable -> the typed assignment payload."""
        for it in items:
            if isinstance(it, AssignClause):
                return it
        raise ValueError(f"interact_assign_variable expected an assignment payload; got: {items}")

    def interact_flag(self, items: list[TransformerItem]) -> FlagClause:
        """Grammar interact_flag -> flag with name, optional extra, and tail.

        The flag name is the leading NAME terminal, which arrives as a ``str``
        after token coercion and must land in ``name`` rather than ``tail``.
        """
        name: str | None = None
        extra: str | None = None
        tail: Tail | None = None
        for it in items:
            if isinstance(it, Token) and it.type in (const.KEY_STRING, const.KEY_SIGNED_INT):
                extra = it.value
            elif name is None and isinstance(it, str):
                name = str(it)
            elif not isinstance(it, Token):
                tail = cast(Tail, it)
        if name is None:
            raise ValueError(f"interact_flag expected a flag name; got: {items!r}")
        return FlagClause(name=name, extra=extra, tail=tail)

    def interact_scale_selector(self, items: list[TransformerItem]) -> ScaleSelector:
        """Grammar interact_scale_selector -> scale mode."""
        for it in items:
            if isinstance(it, Token):
                folded = str(it).casefold()
                if folded == const.GRAMMAR_VALUE_RELATIVE.casefold():
                    return ScaleSelector("relative")
                if folded == const.GRAMMAR_VALUE_ABS.casefold():
                    return ScaleSelector("abs")
        raise ValueError(f"interact_scale_selector expected Relative_/Abs_; got: {items!r}")

    def interact_pick_button(self, items: list[TransformerItem]) -> PickButton:
        """Grammar interact_pick_button -> pick-button clause.

        `VarName` is a postfix marker, so the string is a reference when it is
        present and a literal otherwise.
        """
        text: str | None = None
        is_reference = False
        for it in items:
            # Lark tokens subclass ``str``, so the token check must come first.
            if isinstance(it, Token):
                if it.type == const.TOKEN_VARNAME:
                    is_reference = True
                continue
            if isinstance(it, str) and text is None:
                text = it
        if text is None:
            raise ValueError(f"interact_pick_button expected a STRING; got: {items!r}")
        return PickButton(value=text, is_reference=is_reference)

    def interact_value_line(self, items: list[TransformerItem]) -> Tail:
        """Grammar interact_value_line -> the single value or bound tail."""
        for item in items:
            if not isinstance(item, Token):
                return cast(Tail, item)
        raise ValueError(f"interact_value_line expected a value; got: {items!r}")

    def layer_info(self, items: list[TransformerItem]) -> int:
        """Grammar layer_info -> int layer number."""
        for it in items:
            if isinstance(it, int) and not isinstance(it, bool):
                return it
        raise ValueError(f"layer_info expected an int; got: {items}")

    def seq_control_opt(self, items: list[TransformerItem]) -> TransformerTree:
        """Grammar seq_control_opt -> Tree of optional SEQ_CONTROL/SEQTIMER."""
        return cast(TransformerTree, Tree(const.KEY_SEQ_CONTROL_OPS, cast(list[Any], items)))

    def codeblock_coord(self, items: list[TransformerItem]) -> tuple[float, float]:
        """Grammar codeblock_coord -> (x, y) coordinate pair."""
        items_filtered: list[object] = [v for v in items if not isinstance(v, Token)]
        if len(items_filtered) < 2:
            raise ValueError(f"codeblock_coord expected 2 coordinate values; got {len(items_filtered)}")
        return (_as_float(items_filtered[0]), _as_float(items_filtered[1]))

    def objsizedef(self, items: list[TransformerItem]) -> tuple[float, float]:
        """Grammar objsizedef -> (width, height) size pair."""
        items_filtered: list[object] = [v for v in items if not isinstance(v, Token)]
        if len(items_filtered) < 2:
            raise ValueError(f"objsizedef expected 2 size values; got {len(items_filtered)}")
        return (_as_float(items_filtered[0]), _as_float(items_filtered[1]))


GraphicsInteractMixin = _GraphicsInteractMixin
