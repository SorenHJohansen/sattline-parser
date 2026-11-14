"""Shared helpers for the parser-core test modules.

Only helpers that more than one test module actually uses live here. Library
symbols are imported from their real modules by each test, so this module never
becomes a second public surface for the package.

``reportUnusedClass`` and ``reportUnusedFunction`` are disabled at file scope
because every helper here exists to be imported by another test module, and
Pyright does not count cross-module use of underscore-prefixed names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

from lark import Token, Tree

from sattline_parser.api import create_parser
from sattline_parser.models.ast_model import BasePicture, ModuleHeader
from sattline_parser.transformer._expressions_mixin import ExpressionsMixin
from sattline_parser.transformer._graphics_interact_mixin import GraphicsInteractMixin
from sattline_parser.transformer._module_assembly_mixin import ModuleAssemblyMixin
from sattline_parser.transformer._module_header_mixin import ModuleHeaderMixin
from sattline_parser.transformer._module_layout_mixin import ModuleLayoutMixin
from sattline_parser.transformer._sfc_mixin import SFCMixin
from sattline_parser.transformer._tokens_mixin import TokensMixin
from sattline_parser.transformer.sl_transformer import SLTransformer


class _TextParser(Protocol):
    """The slice of ``Lark`` these helpers use.

    Lark's ``LarkInput`` alias leaves its text type parameter unresolved, so
    strict mode sees ``Lark.parse`` as partially unknown. This protocol pins the
    call shape the tests actually use.
    """

    def parse(self, text: str) -> Tree[Token]: ...


def _parse_to_basepicture(text: str) -> BasePicture:
    parser = cast(_TextParser, create_parser())
    tree = parser.parse(text)
    return cast(BasePicture, SLTransformer().transform(tree))


def _repo_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


class _ModulesHarness(ModuleHeaderMixin, ModuleAssemblyMixin, ModuleLayoutMixin):
    """Direct harness for the composed module mixins."""


class _GraphicsHarness(GraphicsInteractMixin):
    """Direct harness for the graphics/interact mixin."""


class _TokensHarness(TokensMixin):
    pass


class _ExpressionsHarness(ExpressionsMixin):
    pass


class _SFCHarness(SFCMixin):
    pass


def _module_header(name: str = "Module") -> ModuleHeader:
    return ModuleHeader(name=name, invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0))


__all__ = [
    "_ExpressionsHarness",
    "_GraphicsHarness",
    "_ModulesHarness",
    "_SFCHarness",
    "_TokensHarness",
    "_module_header",
    "_parse_to_basepicture",
    "_repo_path",
]
