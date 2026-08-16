"""Graphics and interact mixin for SLTransformer.

Handles graphics object construction, coordinate handling, interact object building,
and layout specification.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeGuard, cast

from lark import Token, Tree

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import GraphObject, InteractObject

from ._comments_mixin import is_comment_tree

TransformerItem = object
TransformerTree = Tree[object]
CoordPair = tuple[float, float]
CoordBox = tuple[CoordPair, CoordPair]


class _CoordOwner(Protocol):
    def _extract_coord_payloads(self, items: list[TransformerItem]) -> tuple[list[object], list[object]]: ...

    def _merge_tails(self, *tail_groups: list[object]) -> list[object]: ...

    def _collect_invar_enable_tails(self, nodes: list[TransformerItem]) -> list[object]: ...


def _coord_parts(owner: object, items: list[TransformerItem]) -> tuple[list[object], list[object]]:
    typed_owner = cast(_CoordOwner, owner)
    payloads, tails = typed_owner._extract_coord_payloads(items)  # pyright: ignore[reportPrivateUsage]
    return list(payloads), list(tails)


def _merged_tails(owner: object, items: list[TransformerItem], coord_tails: list[object]) -> list[object] | None:
    typed_owner = cast(_CoordOwner, owner)
    invar_enable_tails = typed_owner._collect_invar_enable_tails(items)  # pyright: ignore[reportPrivateUsage]
    return typed_owner._merge_tails(coord_tails, invar_enable_tails)  # pyright: ignore[reportPrivateUsage]


def _graph_properties(obj: GraphObject) -> dict[str, object]:
    return obj.properties


def _procedure_payload(value: Any) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value).get(const.KEY_PROCEDURE_CALL)
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def _tree_children(tree: TransformerTree) -> list[object]:
    return cast(list[object], tree.children)


def _is_coord_pair(value: object) -> TypeGuard[CoordPair]:
    if not isinstance(value, tuple):
        return False
    pair = cast(tuple[object, ...], value)
    return len(pair) == 2 and all(isinstance(item, int | float) for item in pair)


def _is_coord_box(value: object) -> TypeGuard[CoordBox]:
    if not isinstance(value, tuple):
        return False
    coords = cast(tuple[object, ...], value)
    return len(coords) == 2 and all(_is_coord_pair(item) for item in coords)


def _as_float(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    raise ValueError(f"Expected a numeric coordinate value; got {type(value).__name__}")


class _GraphicsInteractMixin:
    """Mixin providing graphics and interact object transformation methods."""

    #: Keys merged from the ``common_properties`` rule into GraphObject properties.
    _COMMON_PROPERTY_KEYS = ("layer", "colours", const.TREE_TAG_ENABLE)

    def common_properties(self, items: list[TransformerItem]) -> dict[str, object]:
        """Grammar common_properties -> merged dict of layer/enable/colour content.

        Un-modeled colour trees are preserved verbatim under ``colours`` so no
        source data is silently discarded.
        """
        merged: dict[str, object] = {}
        colours: list[object] = []
        for it in items:
            if is_comment_tree(it):
                continue
            if isinstance(it, int):
                merged["layer"] = it
            elif isinstance(it, dict):
                merged.update(cast(dict[str, object], it))
            elif isinstance(it, Tree):
                colours.append(cast(object, it))
        if colours:
            merged["colours"] = colours
        return merged

    def _apply_common_properties(self, properties: dict[str, object], items: list[TransformerItem]) -> None:
        for it in items:
            if not isinstance(it, dict):
                continue
            payload = cast(dict[str, object], it)
            for key in self._COMMON_PROPERTY_KEYS:
                if key in payload and payload[key] is not None:
                    properties[key] = payload[key]

    def text_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar text_object -> GraphObject (TEXTOBJECT with text and coordinates)."""
        go = GraphObject(const.GRAMMAR_VALUE_TEXTOBJECT)
        properties = _graph_properties(go)

        # Coordinates ((x,y),(w,h))
        coord_payloads, coord_tails = _coord_parts(self, items)
        for it in coord_payloads:
            if _is_coord_box(it):
                properties[const.KEY_COORDS] = it
                break

        # Collect tails (Enable_/InVar_ etc.) across the object
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            properties[const.KEY_TAILS] = tails

        self._apply_common_properties(properties, items)

        # Pair each VARNAME with the nearest preceding top-level text (STRING or text_content)
        text_vars: list[str] = []

        def _extract_text_from_node(node: object) -> str:
            if isinstance(node, str):
                return node
            if isinstance(node, Tree) and node.data == const.TREE_TAG_TEXT_CONTENT:
                for ch in _tree_children(cast(TransformerTree, node)):
                    if isinstance(ch, str):
                        return ch
            node_type = type(cast(object, node)).__name__
            raise ValueError(f"_extract_text_from_node expected a str or a 'text_content' node; got {node_type}")

        for i, it in enumerate(items):
            if isinstance(it, Token) and it.type == const.TOKEN_VARNAME:
                j = i - 1
                while j >= 0:
                    prev = items[j]
                    if is_comment_tree(prev):
                        j -= 1
                        continue
                    s = _extract_text_from_node(prev)
                    if s:
                        text_vars.append(s)
                        break
                    j -= 1

        if text_vars:
            properties["text_vars"] = text_vars
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
        go = GraphObject(const.GRAMMAR_VALUE_RECTANGLEOBJECT)
        properties = _graph_properties(go)
        coord_payloads, coord_tails = _coord_parts(self, items)
        for it in coord_payloads:
            if _is_coord_box(it):
                properties[const.KEY_COORDS] = it
                break
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            properties[const.KEY_TAILS] = tails
        self._apply_common_properties(properties, items)
        return go

    def line_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar line_object -> GraphObject (LINEOBJECT)."""
        go = GraphObject(const.GRAMMAR_VALUE_LINEOBJECT)
        properties = _graph_properties(go)
        coord_payloads, coord_tails = _coord_parts(self, items)
        for it in coord_payloads:
            if _is_coord_box(it):
                properties[const.KEY_COORDS] = it
                break
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            properties[const.KEY_TAILS] = tails
        self._apply_common_properties(properties, items)
        return go

    def oval_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar oval_object -> GraphObject (OVALOBJECT)."""
        go = GraphObject(const.GRAMMAR_VALUE_OVALOBJECT)
        properties = _graph_properties(go)
        coord_payloads, coord_tails = _coord_parts(self, items)
        for it in coord_payloads:
            if _is_coord_box(it):
                properties[const.KEY_COORDS] = it
                break
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            properties[const.KEY_TAILS] = tails
        self._apply_common_properties(properties, items)
        return go

    def polygon_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar polygon_object -> GraphObject (POLYGONOBJECT)."""
        go = GraphObject(const.GRAMMAR_VALUE_POLYGONOBJECT)
        properties = _graph_properties(go)
        _coord_payloads, coord_tails = _coord_parts(self, items)
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            properties[const.KEY_TAILS] = tails
        self._apply_common_properties(properties, items)
        return go

    def segment_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar segment_object -> GraphObject (SEGMENTOBJECT)."""
        go = GraphObject(const.GRAMMAR_VALUE_SEGMENTOBJECT)
        properties = _graph_properties(go)
        coord_payloads, coord_tails = _coord_parts(self, items)
        for it in coord_payloads:
            if _is_coord_box(it):
                properties[const.KEY_COORDS] = it
                break
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            properties[const.KEY_TAILS] = tails
        self._apply_common_properties(properties, items)
        return go

    def composite_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar composite_object -> GraphObject (COMPOSITEOBJECT)."""
        go = GraphObject(const.GRAMMAR_VALUE_COMPOSITEOBJECT)
        properties = _graph_properties(go)
        _coord_payloads, coord_tails = _coord_parts(self, items)
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            properties[const.KEY_TAILS] = tails
        self._apply_common_properties(properties, items)
        return go

    def graph_object(self, items: list[TransformerItem]) -> GraphObject:
        """Grammar graph_object -> GraphObject with optional layer."""
        obj: GraphObject | None = None
        layer: int | None = None
        for it in items:
            if isinstance(it, GraphObject) and obj is None:
                obj = it
            elif isinstance(it, int):
                layer = it

        if obj is None:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"graph_object expected a GraphObject in items; got: {types}")

        if layer is not None:
            _graph_properties(obj)["layer"] = layer

        return obj

    def graph_objects(self, items: list[TransformerItem]) -> list[GraphObject]:
        """Grammar graph_objects -> list of GraphObjects."""
        return [it for it in items if isinstance(it, GraphObject)]

    def interact_objects(self, items: list[TransformerItem]) -> list[InteractObject]:
        """Grammar interact_objects -> list of InteractObjects."""
        out: list[InteractObject] = []
        for it in items:
            if isinstance(it, InteractObject):
                out.append(it)
            elif isinstance(it, Tree):
                children = _tree_children(cast(TransformerTree, it))
                for child in children:
                    if isinstance(child, InteractObject):
                        out.append(child)
        return out

    def _collect_combutproc_tail(self, it: object, props: dict[str, object]) -> dict[str, object] | None:
        """Classify a combutproc tail item; returns an updated procedure dict when found."""
        proc_payload = _procedure_payload(it)
        if proc_payload is not None:
            return proc_payload
        if isinstance(it, int):
            cast(list[object], props.setdefault("layers", [])).append(it)
        elif isinstance(it, dict):
            if const.KEY_ASSIGN in it:
                cast(list[object], props.setdefault("assigns", [])).append(cast(object, it))
            elif const.TREE_TAG_ENABLE in it:
                cast(list[object], props.setdefault("enables", [])).append(cast(object, it))
            else:
                cast(list[object], props.setdefault("flags", [])).append(cast(object, it))
        elif isinstance(it, Tree) and it.data in ("outline_colour", "fill_colour"):
            cast(list[object], props.setdefault("colours", [])).append(cast(object, it))
        return None

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
        props: dict[str, object] = {}
        coords: list[object] = []
        proc: dict[str, object] | None = None
        _coord_payloads, coord_tails = _coord_parts(self, items)
        for it in items:
            if isinstance(it, tuple):
                coords.append(cast(tuple[object, ...], it))
            elif isinstance(it, dict) and const.KEY_COORDS in it:
                payload = cast(dict[str, object], it)
                coords.append(payload[const.KEY_COORDS])
            elif isinstance(it, list):
                for sub in cast(list[object], it):
                    proc_payload = self._collect_combutproc_tail(sub, props)
                    if proc_payload is not None:
                        proc = proc_payload
            else:
                proc_payload = self._collect_combutproc_tail(cast(object, it), props)
                if proc_payload is not None:
                    proc = proc_payload
        props[const.KEY_COORDS] = coords or None
        if proc:
            props[const.KEY_PROCEDURE] = proc
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            props[const.KEY_TAILS] = tails
        return InteractObject(type=const.GRAMMAR_VALUE_COMBUTPROC, properties=props)

    def procedure_call(self, items: list[TransformerItem]) -> dict[str, dict[str, object]]:
        """Grammar procedure_call -> dict with procedure call details.

        The procedure name is the leading NAME terminal (arrives as a ``str``
        after token coercion) and must never be buried in ``args``.
        """
        name: str | None = None
        args: list[object] = []
        for it in items:
            if name is None:
                if isinstance(it, Token) and it.type == "NAME":
                    name = it.value
                elif isinstance(it, str) and not isinstance(it, Token):
                    name = it
                else:
                    args.append(it)
            else:
                args.append(it)
        return {const.KEY_PROCEDURE_CALL: {const.KEY_NAME: name, const.KEY_ARGS: args}}

    def invar(self, items: list[TransformerItem]) -> object:
        """Grammar invar -> connected_variable or variable reference."""
        for it in items:
            if not isinstance(it, Token):
                return it
        raise ValueError(f"invar expected a connected_variable child; got: {items}")

    def enable(self, items: list[TransformerItem]) -> dict[str, object]:
        """Grammar enable -> ENABLE_PREFIX '=' BOOL (invar | enable_expression)."""
        val: bool | None = None
        tail: object | None = None
        for it in items:
            if isinstance(it, bool):
                val = it
            elif not isinstance(it, Token):
                tail = it
        return {
            const.TREE_TAG_ENABLE: bool(val) if val is not None else True,
            const.KEY_TAIL: tail,
        }

    def enable_expression(self, items: list[TransformerItem]) -> object:
        """Grammar enable_expression -> expression within enable context."""
        for it in items:
            if not isinstance(it, Token):
                return it
        raise ValueError(f"enable_expression expected an expression child; got: {items}")

    def interact_simple_item(self, items: list[TransformerItem]) -> InteractObject:
        """Grammar interact_simple_item -> InteractObject (button, checkbox, textbox, etc.)."""
        itype: str | None = None
        coords: list[object] = []
        body: list[object] = []
        _coord_payloads, coord_tails = _coord_parts(self, items)
        for it in items:
            if itype is None and isinstance(it, Token):
                itype = it.value
            elif itype is None and isinstance(it, Tree) and it.data == "interact_type_simple":
                for child in _tree_children(cast(TransformerTree, it)):
                    if isinstance(child, Token):
                        itype = child.value
                        break
            elif isinstance(it, tuple):
                coords.append(cast(tuple[object, ...], it))
            elif isinstance(it, dict) and const.KEY_COORDS in it:
                coords.append(cast(dict[str, object], it)[const.KEY_COORDS])
            elif isinstance(it, Tree) and it.data == const.TREE_TAG_INTERACT_BODY_SEQ:
                tree = cast(TransformerTree, it)
                for child in _tree_children(tree):
                    body.append(child)
            elif isinstance(it, list):
                for child in cast(list[object], it):
                    body.append(child)
        if itype is None:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"interact_simple_item expected an interactor type token; got: {types}")
        props: dict[str, object] = {const.KEY_COORDS: coords or None, const.KEY_BODY: body or None}
        tails = _merged_tails(self, items, coord_tails)
        if tails:
            props[const.KEY_TAILS] = tails
        return InteractObject(type=itype, properties=props)

    def interact_assign_variable_tailed(self, items: list[TransformerItem]) -> dict[str, object | None]:
        """Grammar interact_assign_variable_tailed -> variable assignment with tail."""
        name: str | None = None
        val: object | None = None
        tail: object | None = None
        for it in items:
            if isinstance(it, str) and name is None:
                name = it
            elif not isinstance(it, Token) and val is None:
                val = it
            elif not isinstance(it, Token):
                tail = it
        return {const.KEY_NAME: name, const.KEY_VALUE: val, const.KEY_TAIL: tail}

    def interact_assign_variable_plain(self, items: list[TransformerItem]) -> dict[str, object | None]:
        """Grammar interact_assign_variable_plain -> variable assignment without tail."""
        name: str | None = None
        val: object | None = None
        for it in items:
            if isinstance(it, str) and name is None:
                name = it
            elif not isinstance(it, Token) and val is None:
                val = it
        return {const.KEY_NAME: name, const.KEY_VALUE: val, const.KEY_TAIL: None}

    def interact_assign_variable(self, items: list[TransformerItem]) -> dict[str, object]:
        """Grammar interact_assign_variable -> assignment payload wrapper."""
        for it in items:
            if isinstance(it, dict) and const.KEY_NAME in it:
                return {const.KEY_ASSIGN: cast(dict[str, object], it)}
        raise ValueError(f"interact_assign_variable expected an assignment payload; got: {items}")

    def interact_flag(self, items: list[TransformerItem]) -> dict[str, object | None]:
        """Grammar interact_flag -> flag with name, optional extra, and tail.

        The flag name is the leading NAME terminal, which arrives as a ``str``
        after token coercion and must land in ``name`` rather than ``tail``.
        """
        name: str | None = None
        extra: str | None = None
        tail: object | None = None
        for it in items:
            if isinstance(it, Token) and it.type == const.KEY_NAME and name is None:
                name = it.value
            elif isinstance(it, Token) and it.type in (
                const.KEY_STRING,
                const.KEY_SIGNED_INT,
            ):
                extra = it.value
            elif isinstance(it, str) and name is None:
                name = it
            elif not isinstance(it, Token):
                tail = it
        return {const.KEY_NAME: name, const.KEY_EXTRA: extra, const.KEY_TAIL: tail}

    def interact_value_line(self, items: list[TransformerItem]) -> list[TransformerItem]:
        """Grammar interact_value_line -> list of interact value items."""
        return list(items)

    def layer_info(self, items: list[TransformerItem]) -> int:
        """Grammar layer_info -> int layer number."""
        for it in items:
            if isinstance(it, int):
                return it
        raise ValueError(f"layer_info expected an int; got: {items}")

    def seq_control_opt(self, items: list[TransformerItem]) -> TransformerTree:
        """Grammar seq_control_opt -> Tree of optional SEQ_CONTROL/SEQTIMER."""
        return cast(TransformerTree, Tree(const.KEY_SEQ_CONTROL_OPS, cast(list[Any], items)))

    def codeblock_coord(self, items: list[TransformerItem]) -> tuple[float, float]:
        """Grammar codeblock_coord -> (x, y) coordinate pair."""
        # Filter out Tokens first
        items_filtered: list[object] = [v for v in items if not isinstance(v, Token)]
        if len(items_filtered) < 2:
            raise ValueError(f"codeblock_coord expected 2 coordinate values; got {len(items_filtered)}")
        return (_as_float(items_filtered[0]), _as_float(items_filtered[1]))

    def objsizedef(self, items: list[TransformerItem]) -> tuple[float, float]:
        """Grammar objsizedef -> (width, height) size pair."""
        # Filter out Tokens first
        items_filtered: list[object] = [v for v in items if not isinstance(v, Token)]
        if len(items_filtered) < 2:
            raise ValueError(f"objsizedef expected 2 size values; got {len(items_filtered)}")
        return (_as_float(items_filtered[0]), _as_float(items_filtered[1]))

    def two_layers(self, items: list[TransformerItem]) -> dict[str, float]:
        """Grammar two_layers -> dict with the layer limit value.

        The rule is ``TWO_LAYERS LAYERLIMIT "=" REAL``; the numeric value must
        never be dropped (it feeds ``ModuleDef.seq_layers``).
        """
        value: float | None = None
        for it in items:
            if isinstance(it, int | float):
                value = float(it)
        if value is None:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"two_layers expected a numeric layer value; got: {types}")
        return {const.GRAMMAR_VALUE_TWO_LAYERS: value}


GraphicsInteractMixin = _GraphicsInteractMixin
