"""Module layout and module-definition helpers for the SattLine transformer."""

# ruff: noqa: N802

from __future__ import annotations

from typing import Literal, cast

from lark import Token, Tree

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import GraphObject, InteractObject, ModuleDef
from sattline_parser.models.clauses import (
    ClippingClause,
    CoordBox,
    CoordPair,
    Grid,
    ModuleOptions,
    SeqLayers,
    TwoLayers,
    Zoomable,
    ZoomLimits,
)
from sattline_parser.models.tails import ClipValue, CoordinateClipping, LitStringTail, Tail, VarTail

from ._module_shared import (
    CoordTail,
    InterimCoords,
    TransformerItem,
    TransformerTree,
    coord_pair,
)

_OUTVAR_TOKEN = "OUTVAR_PREFIX"  # nosec B105 - grammar token literal, not a credential
_PREFIX_TOKENS = ("INVAR_PREFIX", _OUTVAR_TOKEN)


def _module_options(items: list[TransformerItem]) -> ModuleOptions:
    """Merge every option payload that reached a ``moduledef_option(s)`` rule."""
    merged = ModuleOptions()
    for payload in items:
        if isinstance(payload, ModuleOptions):
            merged = merged.merge(payload)
        else:
            merged = merged.merge(ModuleOptions.from_option(payload))
    return merged


def _split_coordinate_items(items: list[TransformerItem]) -> tuple[list[float], list[Tail]]:
    """Split a ``coordinates``/``invoke_coord`` run into numbers and tails.

    ``CoordTail`` wrappers keep numeric literal tails out of the coordinate
    values, which matters because Lark drops the separating commas.
    """
    values: list[float] = []
    tails: list[Tail] = []
    for item in items:
        if isinstance(item, CoordTail):
            tails.append(item.value)
        elif isinstance(item, CoordinateClipping):
            tails.extend(item.tails)
        elif isinstance(item, int | float):
            values.append(float(item))
    return values, tails


def _float_values(items: list[TransformerItem]) -> list[float]:
    return [float(item) for item in items if isinstance(item, int | float)]


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
        nums, tails = _split_coordinate_items(items)
        if len(nums) < 2:
            raise ValueError(f"coordinates missing REAL values (got {len(nums)})")
        return InterimCoords((nums[0], nums[1]), tails or None)

    def origo_size_pair(self, items: list[TransformerItem]) -> InterimCoords:
        """Grammar origo_size_pair -> ((x, y), (w, h)) with coordinate tails."""
        coords: list[CoordPair] = []
        tails: list[Tail] = []
        for item in items:
            if not isinstance(item, InterimCoords):
                continue
            pair = coord_pair(item.coords)
            if pair is not None:
                coords.append(pair)
                if item.tails:
                    tails.extend(item.tails)
        if len(coords) != 2:
            raise ValueError(f"origo_size_pair expected 2 coordinate pairs, found {len(coords)}")
        return InterimCoords((coords[0], coords[1]), tails or None)

    def invoke_coord(self, items: list[TransformerItem]) -> InterimCoords:
        """Grammar invoke_coord -> five-value invocation coordinate with tails."""
        nums, tails = _split_coordinate_items(items)
        if len(nums) < 5:
            raise ValueError(f"invoke_coord expected 5 REALs, found {len(nums)}")
        return InterimCoords(
            cast(tuple[float, float, float, float, float], tuple(nums[:5])),
            tails or None,
        )

    def coord_invar_tail(self, items: list[TransformerItem]) -> CoordTail:
        """Grammar coord_invar_tail -> one bound or computed coordinate tail."""
        saw_prefix = False
        direction: Literal["in", "out"] = "in"
        value: object | None = None
        for item in items:
            if isinstance(item, Token):
                if item.type == _OUTVAR_TOKEN:
                    direction = "out"
                if item.type in _PREFIX_TOKENS:
                    saw_prefix = True
                continue
            if value is None:
                value = item
        if value is None:
            raise ValueError("coord_invar_tail expected connected variable or value")
        if not saw_prefix:
            return CoordTail(cast(Tail, value))
        if not isinstance(value, str | bool | int | float | LitStringTail):
            raise ValueError(f"coord_invar_tail expected a literal after InVar_/OutVar_; got: {value!r}")
        return CoordTail(VarTail(direction, value))

    def coord_clippingbounds(self, items: list[TransformerItem]) -> CoordinateClipping:
        """Grammar coord_clippingbounds -> the nested clipping specification."""
        for item in items:
            if isinstance(item, CoordinateClipping):
                return item
        raise ValueError("coord_clippingbounds expected clip values; got no payload")

    def clip_value_tailed(self, items: list[TransformerItem]) -> ClipValue:
        """Grammar clip_value_tailed -> a numeric value and its coordinate tail."""
        value = next((float(item) for item in items if isinstance(item, int | float)), None)
        if value is None:
            raise ValueError("clip_value_tailed expected a REAL value")
        tail = next((item.value for item in items if isinstance(item, CoordTail)), None)
        return ClipValue(value, tail)

    def clip_value_plain(self, items: list[TransformerItem]) -> ClipValue:
        """Grammar clip_value_plain -> a numeric value without a tail."""
        value = next((float(item) for item in items if isinstance(item, int | float)), None)
        if value is None:
            raise ValueError("clip_value_plain expected a REAL value")
        return ClipValue(value)

    def clip_value(self, items: list[TransformerItem]) -> ClipValue:
        """Grammar clip_value -> pass through the single clip value."""
        for item in items:
            if isinstance(item, ClipValue):
                return item
        raise ValueError("clip_value expected a clip value payload")

    def clip_values(self, items: list[TransformerItem]) -> CoordinateClipping:
        """Grammar clip_values -> every nested clipping value."""
        return CoordinateClipping(tuple(item for item in items if isinstance(item, ClipValue)))

    def clippingbounds(self, items: list[TransformerItem]) -> ClippingClause:
        """Grammar clippingbounds -> the resolved corners and their corner tails."""
        for item in items:
            if isinstance(item, InterimCoords):
                return ClippingClause(cast(CoordBox, item.coords), tuple(item.tails or ()))
        raise ValueError("clippingbounds expected a payload; got no items")

    def seq_layers(self, items: list[TransformerItem]) -> SeqLayers:
        """Grammar seq_layers -> the sequence layer mapping."""
        value = items[-1]
        if isinstance(value, int | float):
            return SeqLayers(float(value))
        if isinstance(value, dict):
            return SeqLayers(cast(dict[str, float], value))
        raise ValueError(f"seq_layers expected a layer mapping or REAL; got: {value!r}")

    def zoomlimits(self, items: list[TransformerItem]) -> ZoomLimits:
        """Grammar zoomlimits -> min/max zoom values."""
        values = _float_values(items)
        if len(values) < 2:
            raise ValueError(f"zoomlimits expected two REAL values; got: {items!r}")
        return ZoomLimits(values[-2], values[-1])

    def ZOOMABLE(self, _: object) -> Zoomable:
        """Grammar ZOOMABLE -> the module's zoomable marker."""
        return Zoomable()

    def grid(self, items: list[TransformerItem]) -> Grid:
        """Grammar grid -> the grid spacing value."""
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

        return Grid(nums[-1])

    def two_layers(self, items: list[TransformerItem]) -> TwoLayers:
        """Grammar two_layers -> the layer limit value.

        The rule is ``TWO_LAYERS LAYERLIMIT "=" REAL``; the numeric value must
        never be dropped (it feeds ``ModuleDef.seq_layers``).
        """
        values = _float_values(items)
        if not values:
            types = ", ".join(type(x).__name__ for x in items)
            raise ValueError(f"two_layers expected a numeric layer value; got: {types}")
        return TwoLayers(values[-1])

    def moduledef_option(self, items: list[TransformerItem]) -> ModuleOptions:
        """Grammar moduledef_option -> the option as a ``ModuleOptions`` delta."""
        return _module_options(items)

    def moduledef_opts(self, items: list[TransformerItem]) -> ModuleOptions:
        """Grammar moduledef_opts -> every module option merged into one payload."""
        return _module_options(items)

    def moduledef_opts_seq(self, items: list[TransformerItem]) -> TransformerTree:
        """Grammar moduledef_opts_seq -> Tree with the merged option payload."""
        return Tree(const.TREE_TAG_MODULEDEF_OPTS_SEQ, [_module_options(items)])

    @staticmethod
    def _apply_clipping_bounds(module_def: ModuleDef, clause: ClippingClause) -> None:
        """Record the resolved ClippingBounds corners and their corner tails.

        Tails go to both :attr:`ModuleDef.clipping_tails`, which validation reads to
        type-check corner expressions, and to the shared ``tails`` property, which
        the graphics/interact consumers already expect.
        """
        module_def.clipping_bounds = clause.bounds
        if not clause.tails:
            return
        module_def.clipping_tails = list(clause.tails)
        property_tails = module_def.properties.get(const.KEY_TAILS)
        if property_tails is not None:
            property_tails.extend(clause.tails)
        else:
            module_def.properties[const.KEY_TAILS] = list(clause.tails)

    @staticmethod
    def _apply_module_options(module_def: ModuleDef, options: ModuleOptions) -> None:
        if options.layer_limit is not None:
            module_def.seq_layers = options.layer_limit
        if options.zoom_limits is not None:
            module_def.zoom_limits = (options.zoom_limits.minimum, options.zoom_limits.maximum)
        if options.zoomable:
            module_def.zoomable = True
        if options.grid is not None:
            module_def.grid = options.grid

    def moduledef(self, items: list[TransformerItem]) -> ModuleDef:
        """Grammar moduledef -> ModuleDef with graphics, layout, and interact objects."""
        module_def = ModuleDef()
        for it in items:
            if isinstance(it, ClippingClause):
                self._apply_clipping_bounds(module_def, it)
            elif isinstance(it, ModuleOptions):
                self._apply_module_options(module_def, it)
            elif isinstance(it, SeqLayers):
                module_def.seq_layers = it.value
            elif isinstance(it, list) and it:
                if isinstance(it[0], GraphObject):
                    module_def.graph_objects = cast(list[GraphObject], it)
                elif isinstance(it[0], InteractObject):
                    module_def.interact_objects = cast(list[InteractObject], it)
        return module_def


__all__ = ["ModuleLayoutMixin"]
