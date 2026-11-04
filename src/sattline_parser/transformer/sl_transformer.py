"""Lark transformer that builds the SattLine AST.

Split into responsibility-based mixins for maintainability.
"""

from __future__ import annotations

from typing import Any, TypeGuard, cast

from lark import Tree
from lark.visitors import Transformer_NonRecursive

from sattline_parser.models.ast_model import BasePicture

from . import _module_shared as _module_shared
from ._comments_mixin import CommentsMixin
from ._expressions_mixin import ExpressionsMixin
from ._graphics_interact_mixin import GraphicsInteractMixin
from ._module_assembly_mixin import ModuleAssemblyMixin
from ._module_header_mixin import ModuleHeaderMixin
from ._module_layout_mixin import ModuleLayoutMixin
from ._module_shared import TransformerItem, TransformerTree, tree_children
from ._sfc_mixin import SFCMixin
from ._tokens_mixin import TokensMixin

__all__ = [
    "SLTransformer",
    "_extract_program_name_from_header_lines",
    "_is_tree",
    "_iter_tree_children",
    "_strip_quoted",
    "flatten_items",
    "meta_span",
]

flatten_items = _module_shared.flatten_items
meta_span = _module_shared.meta_span


def _is_tree(node: object) -> TypeGuard[TransformerTree]:
    """Check if node is a Lark Tree."""
    return isinstance(node, Tree)


def _iter_tree_children(node: object) -> tuple[TransformerItem, ...]:
    """Yield tree children when given a Tree-like node, otherwise return an empty tuple."""
    if not _is_tree(node):
        return ()
    return tuple(tree_children(node))


def _strip_quoted(text: str) -> str:
    """Remove wrapping double quotes and unescape doubled inner quotes."""
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('""', '"').rstrip("\n")
    return text


_EXPORTED_HELPERS = (flatten_items, _iter_tree_children, meta_span, _strip_quoted)


def _extract_program_name_from_header_lines(tree: TransformerTree) -> str | None:
    """Extract program name from the program_date_line header string."""
    for child in tree_children(tree):
        if _is_tree(child) and child.data == "program_date_line":
            for token in _iter_tree_children(child):
                raw = _strip_quoted(str(token))
                for field in raw.split(","):
                    name, separator, value = field.partition(":")
                    if separator and name.strip().casefold() == "name":
                        program_name = value.strip()
                        if program_name:
                            return program_name
    return None


class SLTransformer(
    TokensMixin,
    CommentsMixin,
    ExpressionsMixin,
    SFCMixin,
    ModuleHeaderMixin,
    ModuleAssemblyMixin,
    ModuleLayoutMixin,
    GraphicsInteractMixin,
    Transformer_NonRecursive[Any, Any],
):
    """Lark transformer building SattLine AST from parsed grammar.

    The base is Lark's non-recursive transformer, so a deeply parenthesized
    parse tree is reduced with an explicit post-order stack. The mixin methods
    and their bottom-up call order are unchanged.

    Mixins provide grouped method implementations by responsibility:
    - TokensMixin: token coercion and literal conversion
    - ExpressionsMixin: expressions, values, and statements
    - SFCMixin: sequence function chart nodes
    - ModuleHeaderMixin: module headers and invocation argument metadata
    - ModuleAssemblyMixin: module-body normalization and AST assembly
    - ModuleLayoutMixin: layout, coordinates, and ModuleDef parsing
    - GraphicsInteractMixin: graphics and interact object handling
    """

    def __init__(self) -> None:
        super().__init__()

    def start(self, items: list[TransformerItem]) -> BasePicture:
        """Grammar start -> BasePicture root from parsed program."""
        program_name: str | None = None
        base_picture: BasePicture | None = None
        for item in items:
            if isinstance(item, Tree) and item.data == "header_lines":
                program_name = _extract_program_name_from_header_lines(cast(TransformerTree, item))
            elif isinstance(item, BasePicture):
                base_picture = item
        if base_picture is not None:
            base_picture.program_name = program_name
            return base_picture
        types = ", ".join(type(item).__name__ for item in items)
        raise ValueError(f"start expected a BasePicture; got: {types}")
