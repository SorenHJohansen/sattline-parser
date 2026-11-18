"""Module header parsing helpers for the SattLine transformer."""

# ruff: noqa: N802

from __future__ import annotations

from typing import Any, cast

from lark import Token

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import CodeComment, ModuleHeader
from sattline_parser.models.clauses import (
    AssignClause,
    EnableClause,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    ZoomLimits,
)
from sattline_parser.models.tails import Tail

from ._module_shared import InterimCoords, TransformerItem, float_tuple, meta_span, v_args
from ._payloads import Zoomable
from ._tokens_mixin import token_span


class ModuleHeaderMixin:
    """Mixin providing module header and argument transformation methods."""

    def IGNOREMAXMODULE(self, tok: Token) -> ModuleMarker:
        """Grammar IGNOREMAXMODULE terminal -> the ignore-max marker argument."""
        return ModuleMarker(const.GRAMMAR_VALUE_IGNOREMAXMODULE, token_span(tok))

    def LAYERMODULE(self, tok: Token) -> ModuleMarker:
        """Grammar LAYERMODULE terminal -> the layer marker argument."""
        return ModuleMarker(const.GRAMMAR_VALUE_LAYERMODULE, token_span(tok))

    def SYMBOLMODULE(self, tok: Token) -> ModuleMarker:
        """Grammar SYMBOLMODULE terminal -> the symbol marker argument."""
        return ModuleMarker(const.GRAMMAR_VALUE_SYMBOLMODULE, token_span(tok))

    def NON_ZOOMABLE(self, tok: Token) -> ModuleMarker:
        """Grammar NON_ZOOMABLE terminal -> the non-zoomable marker argument."""
        return ModuleMarker(const.GRAMMAR_VALUE_NON_ZOOMABLE, token_span(tok))

    def argument(self, items: list[TransformerItem]) -> TransformerItem | None:
        """Grammar argument rule -> pass through single non-Token child."""
        for it in items:
            if not isinstance(it, Token):
                return it
        return None

    @v_args(meta=True)
    def arguments(self, meta: Any, items: list[TransformerItem]) -> ModuleArguments:
        """Grammar arguments -> the typed content of the invocation argument list.

        The rule repeats, but ``Layer_``, ``Enable_``, ``Module_In_View`` and
        ``ZoomLimits`` are singular properties. A second one is ambiguous, so it
        is rejected rather than silently overwriting the first; the marker and
        assignment lists keep every entry.
        """
        layer: int | None = None
        enable: EnableClause | None = None
        module_in_view: ModuleInViewClause | None = None
        zoom_limits: ZoomLimits | None = None
        zoomable = False
        markers: list[ModuleMarker] = []
        assigns: list[AssignClause] = []
        for it in items:
            if isinstance(it, EnableClause):
                if enable is not None:
                    raise ValueError("module header has more than one Enable_ argument")
                enable = it
            elif isinstance(it, ModuleInViewClause):
                if module_in_view is not None:
                    raise ValueError("module header has more than one Module_In_View argument")
                module_in_view = it
            elif isinstance(it, ZoomLimits):
                if zoom_limits is not None:
                    raise ValueError("module header has more than one ZoomLimits argument")
                zoom_limits = it
            elif isinstance(it, Zoomable):
                zoomable = True
            elif isinstance(it, ModuleMarker):
                markers.append(it)
            elif isinstance(it, AssignClause):
                assigns.append(it)
            elif isinstance(it, int) and not isinstance(it, bool):
                if layer is not None:
                    raise ValueError("module header has more than one Layer_ argument")
                layer = it
        return ModuleArguments(
            layer=layer,
            enable=enable,
            module_in_view=module_in_view,
            zoom_limits=zoom_limits,
            zoomable=zoomable,
            markers=tuple(markers),
            assigns=tuple(assigns),
            span=meta_span(meta),
        )

    @v_args(meta=True)
    def module_header(self, meta: Any, items: list[TransformerItem]) -> ModuleHeader:
        """Grammar module_header -> ModuleHeader with position, arguments, layer, enable."""
        name: str | None = None
        coords5: tuple[float, float, float, float, float] | None = None
        coord_tails: list[Tail] = []
        coordinate_tails: tuple[tuple[Tail, ...], ...] = ()
        arguments = ModuleArguments()
        description_comments: list[CodeComment] = []

        for it in items:
            if isinstance(it, CodeComment):
                description_comments.append(it)
            elif isinstance(it, str) and not isinstance(it, Token):
                if name is None:
                    name = it
            elif isinstance(it, InterimCoords):
                coords = float_tuple(it.coords, 5)
                if coords is not None:
                    coords5 = cast(tuple[float, float, float, float, float], coords)
                    coord_tails.extend(it.tails or ())
                    coordinate_tails = it.coord_tails or ()
            elif isinstance(it, ModuleArguments):
                arguments = it

        if coords5 is None:
            raise ValueError("module_header missing invoke_coord")

        return ModuleHeader(
            name=name or "",
            invoke_coord=coords5,
            declaration_span=meta_span(meta),
            arguments=arguments,
            invoke_coord_tails=coord_tails,
            description_comments=description_comments,
            coordinate_tails=coordinate_tails,
        )


__all__ = ["ModuleHeaderMixin"]
