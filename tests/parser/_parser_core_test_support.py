# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false
"""Tests for grammar coverage and parser-core behaviour.

Covers parse_source_text, source spans, flags, and identifier rules.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, LiteralString, cast

import pytest
from lark import Token, Tree
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken
from lark.tree import Meta

from sattline_parser import (
    fuzz_harness as parser_fuzz_harness,
)
from sattline_parser import (
    parse_source_text as parser_core_parse_source_text,
)
from sattline_parser import (
    source_io as parser_api,
)
from sattline_parser.api import create_parser, parse_source_file
from sattline_parser.formatting.formatter import format_expr, format_list, format_optional, format_seq_nodes
from sattline_parser.grammar import constants as const
from sattline_parser.grammar import constants as parser_const
from sattline_parser.models.ast_model import (
    BasePicture,
    CodeComment,
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
    Sequence,
    SFCAlternative,
    SFCCodeBlocks,
    SFCFork,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
    Simple_DataType,
    SingleModule,
    SourceSpan,
    Variable,
)
from sattline_parser.models.clauses import (
    AssignClause,
    ClippingClause,
    ColourSpec,
    CommonProperties,
    EnableClause,
    FlagClause,
    Grid,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    ModuleOptions,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    SeqLayers,
    TailedClause,
    TwoLayers,
    Zoomable,
    ZoomLimits,
)
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.models.tails import ClipValue, CoordinateClipping, LitStringTail, VarTail
from sattline_parser.preprocessing import preprocess_sl_text, preprocess_source
from sattline_parser.source_document import SourceDocument
from sattline_parser.transformer._expressions_mixin import _ExpressionsMixin
from sattline_parser.transformer._graphics_interact_mixin import _GraphicsInteractMixin
from sattline_parser.transformer._module_assembly_mixin import ModuleAssemblyMixin
from sattline_parser.transformer._module_header_mixin import ModuleHeaderMixin
from sattline_parser.transformer._module_layout_mixin import ModuleLayoutMixin
from sattline_parser.transformer._module_shared import (
    CodeBlockPayload,
    CoordTail,
    GroupConnInfo,
    InterimCoords,
    flatten_items,
    meta_span,
)
from sattline_parser.transformer._sfc_mixin import SFCMixin
from sattline_parser.transformer._tokens_mixin import DEFAULT_INIT, TokensMixin
from sattline_parser.transformer.sl_transformer import (
    SLTransformer,
    _extract_program_name_from_header_lines,
    _iter_tree_children,
    _strip_quoted,
)
from sattline_parser.transformer.sl_transformer import (
    _is_tree as _sl_is_tree,
)
from sattline_parser.transformer.sl_transformer import (
    flatten_items as _sl_flatten_items,
)
from sattline_parser.transformer.sl_transformer import (
    meta_span as _sl_meta_span,
)


def _parse_to_basepicture(text: str):
    parser = create_parser()
    tree = parser.parse(text)
    return SLTransformer().transform(tree)


def _repo_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


_is_tree = _sl_is_tree


class _ModulesHarness(ModuleHeaderMixin, ModuleAssemblyMixin, ModuleLayoutMixin):
    """Direct harness for the composed module mixins."""


class _GraphicsHarness(_GraphicsInteractMixin):
    """Direct harness for the graphics/interact mixin."""


class _TokensHarness(TokensMixin):
    pass


class _ExpressionsHarness(_ExpressionsMixin):
    pass


class _SFCHarness(SFCMixin):
    pass


def _module_header(name: str = "Module") -> ModuleHeader:
    return ModuleHeader(name=name, invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0))


__all__ = [
    "DEFAULT_INIT",
    "Any",
    "AssignClause",
    "Assignment",
    "BasePicture",
    "BinOp",
    "BoolOp",
    "ClipValue",
    "ClippingClause",
    "CodeBlockPayload",
    "CodeComment",
    "ColourSpec",
    "CommonProperties",
    "Compare",
    "CoordTail",
    "CoordinateClipping",
    "DataType",
    "EnableClause",
    "Equation",
    "FlagClause",
    "FloatLiteral",
    "FrameModule",
    "FuncCall",
    "FuncCallStmt",
    "GraphObject",
    "Grid",
    "GroupConnInfo",
    "IfStmt",
    "IntLiteral",
    "InteractObject",
    "InterimCoords",
    "LitStringTail",
    "LiteralString",
    "Meta",
    "ModuleArguments",
    "ModuleAssemblyMixin",
    "ModuleCode",
    "ModuleDef",
    "ModuleHeader",
    "ModuleHeaderMixin",
    "ModuleInViewClause",
    "ModuleLayoutMixin",
    "ModuleMarker",
    "ModuleOptions",
    "ModuleTypeDef",
    "ModuleTypeInstance",
    "NotOp",
    "ParameterMapping",
    "Path",
    "PickButton",
    "ProcedureCall",
    "SFCAlternative",
    "SFCCodeBlocks",
    "SFCFork",
    "SFCMixin",
    "SFCParallel",
    "SFCStep",
    "SFCSubsequence",
    "SFCTransition",
    "SFCTransitionSub",
    "SLTransformer",
    "ScaleSelector",
    "SeqLayers",
    "Sequence",
    "SimpleNamespace",
    "Simple_DataType",
    "SingleModule",
    "SourceDocument",
    "SourceSpan",
    "TailedClause",
    "TernaryOp",
    "Token",
    "TokensMixin",
    "Tree",
    "TwoLayers",
    "UnaryOp",
    "UnexpectedCharacters",
    "UnexpectedEOF",
    "UnexpectedInput",
    "UnexpectedToken",
    "VarRef",
    "VarTail",
    "Variable",
    "ZoomLimits",
    "Zoomable",
    "_ExpressionsHarness",
    "_ExpressionsMixin",
    "_GraphicsHarness",
    "_GraphicsInteractMixin",
    "_ModulesHarness",
    "_SFCHarness",
    "_TokensHarness",
    "_extract_program_name_from_header_lines",
    "_is_tree",
    "_iter_tree_children",
    "_module_header",
    "_parse_to_basepicture",
    "_repo_path",
    "_sl_flatten_items",
    "_sl_is_tree",
    "_sl_meta_span",
    "_strip_quoted",
    "ast",
    "cast",
    "const",
    "create_parser",
    "flatten_items",
    "format_expr",
    "format_list",
    "format_optional",
    "format_seq_nodes",
    "importlib",
    "meta_span",
    "parse_source_file",
    "parser_api",
    "parser_const",
    "parser_core_parse_source_text",
    "parser_fuzz_harness",
    "preprocess_sl_text",
    "preprocess_source",
    "pytest",
    "sys",
]
