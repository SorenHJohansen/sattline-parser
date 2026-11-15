"""Reusable SattLine parser-core package."""

from __future__ import annotations

from sattline_parser.models import NodeVisitor, WalkEvent, iter_child_nodes, walk
from sattline_parser.models.ast_model import BasePicture, SourceSpan
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
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
from sattline_parser.preprocessing import (
    is_compressed,
    preprocess_sl_text,
    preprocess_source,
    render_ide_text,
)
from sattline_parser.transformer.sl_transformer import SLTransformer
from sattline_parser.validation import Diagnostic, DiagnosticCode, validate_basepicture

from .__version__ import __version__
from .api import (
    MAX_SOURCE_DEPTH,
    SourceTooDeepError,
    create_parser,
    describe_parse_error,
    parse_and_validate,
    parse_source_file,
    parse_source_text,
)
from .grammar import constants
from .project import (
    parse_distribution_file,
    parse_distribution_text,
    parse_graphics_file,
    parse_graphics_text,
    resolve_distribution_companion_path,
    resolve_graphics_companion_path,
)
from .serialization import to_json, to_jsonable

__all__ = [
    "MAX_SOURCE_DEPTH",
    "Assignment",
    "BasePicture",
    "BinOp",
    "BoolOp",
    "Compare",
    "Diagnostic",
    "DiagnosticCode",
    "FuncCall",
    "FuncCallStmt",
    "IfStmt",
    "NodeVisitor",
    "NotOp",
    "SLExpression",
    "SLStmt",
    "SLTransformer",
    "SourceSpan",
    "SourceTooDeepError",
    "TernaryOp",
    "UnaryOp",
    "VarRef",
    "WalkEvent",
    "__version__",
    "constants",
    "create_parser",
    "describe_parse_error",
    "is_compressed",
    "iter_child_nodes",
    "parse_and_validate",
    "parse_distribution_file",
    "parse_distribution_text",
    "parse_graphics_file",
    "parse_graphics_text",
    "parse_source_file",
    "parse_source_text",
    "preprocess_sl_text",
    "preprocess_source",
    "render_ide_text",
    "resolve_distribution_companion_path",
    "resolve_graphics_companion_path",
    "to_json",
    "to_jsonable",
    "validate_basepicture",
    "walk",
]
