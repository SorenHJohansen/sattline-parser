"""Module layout and module-definition helpers for the SattLine transformer."""

# ruff: noqa: N802

from __future__ import annotations

from typing import Any, cast

from lark import Token, Tree

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import GraphObject, InteractObject, ModuleDef

from ._module_shared import (
    InterimCoords,
    TransformerItem,
    TransformerTree,
    coord_pair,
)


class ModuleLayoutMixin:
    """Mixin providing module layout and ModuleDef transformation methods."""

    def origo_coord(self, items: list[TransformerItem]) -> list[TransformerItem]:
        """Grammar origo_coord -> coordinate values list."""
        return items

    def size(self, items: list[TransformerItem]) -> list[TransformerItem]:
        """Grammar size -> size values list."""
        return items

    def coordinates(self, items: list[TransformerItem]) -> InterimCoords:
        """Grammar coordinates -> (x, y) with optional coordinate tails."""
        items_filtered = [value for value in items if not isinstance(value, Token)]
        nums = [float(value) for value in items_filtered if isinstance(value, int | float)]
        if len(nums) < 2:
            raise ValueError(f"coordinates missing REAL values (got {len(nums)})")
        tails = cast(list[object], self._extract_coord_tails(cast(list[Any], items)))  # type: ignore[attr-defined]
        return InterimCoords((nums[0], nums[1]), tails or None)

    def origo_size_pair(self, items: list[TransformerItem]) -> InterimCoords:
        """Grammar origo_size_pair -> ((x, y), (w, h)) with coordinate tails."""
        coords: list[tuple[float, float]] = []
        tails: list[Any] = []
        for it in items:
            if isinstance(it, InterimCoords):
                coord = coord_pair(it.coords)
                if coord is not None:
                    coords.append(coord)
                    if it.tails:
                        tails.extend(it.tails)
            elif isinstance(it, Tree) and it.data == const.TREE_TAG_COORDINATES:
                tree = cast(TransformerTree, it)
                nums = [float(x) for x in tree.children if isinstance(x, int | float)]
                if len(nums) >= 2:
                    coords.append((nums[0], nums[1]))
            elif isinstance(it, tuple):
                coord = coord_pair(cast(tuple[object, ...], it))
                if coord is not None:
                    coords.append(coord)
        if len(coords) != 2:
            raise ValueError(f"origo_size_pair expected 2 coordinate pairs, found {len(coords)}")
        return InterimCoords((coords[0], coords[1]), tails or None)

    def invoke_coord(self, items: list[TransformerItem]) -> InterimCoords:
        """Grammar invoke_coord -> five-value invocation coordinate with tails."""
        items_filtered = [value for value in items if not isinstance(value, Token)]
        nums = [float(value) for value in items_filtered if isinstance(value, int | float)]
        if len(nums) < 5:
            raise ValueError(f"invoke_coord expected 5 REALs, found {len(nums)}")
        tails = cast(list[object], self._extract_coord_tails(cast(list[Any], items)))  # type: ignore[attr-defined]
        return InterimCoords(cast(tuple[float, float, float, float, float], tuple(nums[:5])), tails or None)

    def coord_invar_tail(self, items: list[TransformerItem]) -> TransformerItem:
        """Grammar coord_invar_tail -> connected variable value."""
        for it in items:
            if not isinstance(it, Token):
                return it
        raise ValueError("coord_invar_tail expected connected variable or value")

    def coord_clippingbounds(self, items: list[TransformerItem]) -> TransformerTree:
        """Grammar coord_clippingbounds -> Tree of clipping specification."""
        return Tree(const.GRAMMAR_VALUE_CLIPPINGBOUNDS, cast(list[Any], items))

    def clippingbounds(self, items: list[TransformerItem]) -> dict[str, object]:
        """Grammar clippingbounds -> dict with clipping values and tails."""
        payload: InterimCoords | None = None
        for it in items:
            if isinstance(it, InterimCoords):
                payload = it
                break
        if payload is not None:
            return {
                const.GRAMMAR_VALUE_CLIPPINGBOUNDS: payload.coords,
                const.KEY_TAILS: payload.tails or None,
            }
        if not items:
            raise ValueError("clippingbounds expected a payload; got no items")
        return {const.GRAMMAR_VALUE_CLIPPINGBOUNDS: items[-1]}

    def seq_layers(self, items: list[TransformerItem]) -> dict[str, object]:
        """Grammar seq_layers -> dict with sequence layer mapping."""
        return {const.KEY_SEQ_LAYERS: items[-1]}

    def zoomlimits(self, items: list[TransformerItem]) -> dict[str, tuple[TransformerItem, TransformerItem]]:
        """Grammar zoomlimits -> dict with min/max zoom values."""
        values = [it for it in items if not isinstance(it, Token)]
        if len(values) < 2:
            raise ValueError(f"zoomlimits expected two REAL values; got: {items!r}")
        return {const.GRAMMAR_VALUE_ZOOMLIMITS: (values[-2], values[-1])}

    def ZOOMABLE(self, _: object) -> dict[str, bool]:
        """Grammar ZOOMABLE -> dict marking module as zoomable."""
        return {const.GRAMMAR_VALUE_ZOOMABLE: True}

    def grid(self, items: list[TransformerItem]) -> float:
        """Grammar grid -> float grid spacing value."""
        nums: list[float] = []
        for value in items:
            if isinstance(value, Token):
                continue
            if isinstance(value, int | float | str):
                try:
                    nums.append(float(value))
                except ValueError as exc:
                    raise ValueError(f"grid expected a numeric value; got {type(value).__name__}: {value!r}") from exc
                continue
            raise ValueError(f"grid expected a numeric value; got {type(value).__name__}: {value!r}")

        if not nums:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"grid expected at least one numeric value; got: {types}")

        return nums[-1]

    def moduledef_option(self, items: list[TransformerItem]) -> dict[str, object]:
        """Grammar moduledef_option -> merged option dict.

        ``grid`` returns a bare float; it is wrapped under the GRID key so no
        option value is lost.
        """
        merged: dict[str, object] = {}
        for payload in items:
            if isinstance(payload, dict):
                merged.update(cast(dict[str, object], payload))
            elif isinstance(payload, int | float):
                merged[const.GRAMMAR_VALUE_GRID] = float(payload)
        return merged

    def moduledef_opts(self, items: list[TransformerItem]) -> dict[str, object]:
        """Grammar moduledef_opts -> merged dict of all module options."""
        merged: dict[str, object] = {}
        for payload in items:
            if isinstance(payload, dict):
                merged.update(cast(dict[str, object], payload))
        return merged

    def moduledef_opts_seq(self, items: list[TransformerItem]) -> TransformerTree:
        """Grammar moduledef_opts_seq -> Tree with merged option dict."""
        merged: dict[str, object] = {}
        for payload in items:
            if isinstance(payload, dict):
                merged.update(cast(dict[str, object], payload))
        return Tree(const.TREE_TAG_MODULEDEF_OPTS_SEQ, cast(list[Any], [merged]))

    def moduledef(self, items: list[TransformerItem]) -> ModuleDef:
        """Grammar moduledef -> ModuleDef with graphics, layout, and interact objects."""
        module_def = ModuleDef()
        for it in items:
            if isinstance(it, dict) and const.GRAMMAR_VALUE_CLIPPINGBOUNDS in it:
                payload = cast(dict[str, object], it)
                clipping_bounds = payload[const.GRAMMAR_VALUE_CLIPPINGBOUNDS]
                if isinstance(clipping_bounds, tuple):
                    clipping_tuple = cast(tuple[object, ...], clipping_bounds)
                    if len(clipping_tuple) == 2:
                        module_def.clipping_bounds = cast(
                            tuple[tuple[float, float], tuple[float, float]],
                            clipping_tuple,
                        )
                tails = payload.get(const.KEY_TAILS)
                if isinstance(tails, list) and tails:
                    typed_tails = cast(list[object], tails)
                    property_tails = module_def.properties.get(const.KEY_TAILS)
                    if isinstance(property_tails, list):
                        cast(list[object], property_tails).extend(typed_tails)
                    else:
                        module_def.properties[const.KEY_TAILS] = list(typed_tails)
            elif isinstance(it, tuple):
                clipping_tuple = cast(tuple[object, ...], it)
                if len(clipping_tuple) == 2 and all(isinstance(t, tuple) for t in clipping_tuple):
                    module_def.clipping_bounds = cast(
                        tuple[tuple[float, float], tuple[float, float]],
                        clipping_tuple,
                    )
            elif isinstance(it, list) and it:
                if isinstance(it[0], GraphObject):
                    module_def.graph_objects = cast(list[GraphObject], it)
                elif isinstance(it[0], InteractObject):
                    module_def.interact_objects = cast(list[InteractObject], it)
            elif isinstance(it, dict):
                payload = cast(dict[str, object], it)
                if const.GRAMMAR_VALUE_ZOOMLIMITS in payload:
                    zoom_limits = coord_pair(payload[const.GRAMMAR_VALUE_ZOOMLIMITS])
                    if zoom_limits is not None:
                        module_def.zoom_limits = zoom_limits
                if const.GRAMMAR_VALUE_ZOOMABLE in payload:
                    zoomable = payload[const.GRAMMAR_VALUE_ZOOMABLE]
                    if isinstance(zoomable, bool):
                        module_def.zoomable = zoomable
                if const.GRAMMAR_VALUE_GRID in payload and payload[const.GRAMMAR_VALUE_GRID] is not None:
                    grid_value = payload[const.GRAMMAR_VALUE_GRID]
                    if isinstance(grid_value, int | float | str):
                        module_def.grid = float(grid_value)
                if const.KEY_SEQ_LAYERS in payload:
                    layers_value = payload[const.KEY_SEQ_LAYERS]
                    if isinstance(layers_value, dict):
                        module_def.seq_layers = cast(dict[str, float], layers_value)
                    elif isinstance(layers_value, int | float):
                        module_def.seq_layers = float(layers_value)
                if const.GRAMMAR_VALUE_TWO_LAYERS in payload:
                    layers_value = payload[const.GRAMMAR_VALUE_TWO_LAYERS]
                    if isinstance(layers_value, int | float):
                        module_def.seq_layers = float(layers_value)
        return module_def


__all__ = ["ModuleLayoutMixin"]
