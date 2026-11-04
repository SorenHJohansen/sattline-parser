"""Reusable SattLine parser-core package."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING, Any

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
from .project import parse_graphics_file, parse_graphics_text, resolve_graphics_companion_path

if TYPE_CHECKING:
    from . import fuzz_harness as fuzz_harness
    from .fuzz_harness import (
        FuzzResult,
        assert_no_crashes,
        assert_no_timeouts,
        collect_corpus_inputs,
        fuzz_parse_text,
        generate_random_text,
        run_corpus_regression,
        run_random_fuzz,
    )

_FUZZ_EXPORTS = (
    "FuzzResult",
    "assert_no_crashes",
    "assert_no_timeouts",
    "collect_corpus_inputs",
    "fuzz_harness",
    "fuzz_parse_text",
    "generate_random_text",
    "run_corpus_regression",
    "run_random_fuzz",
)
_FUZZ_EXPORT_SET = frozenset(_FUZZ_EXPORTS)


def _load_fuzz_harness() -> ModuleType:
    module = import_module(".fuzz_harness", __name__)
    globals()["fuzz_harness"] = module
    for export_name in _FUZZ_EXPORTS:
        if export_name == "fuzz_harness":
            continue
        globals()[export_name] = getattr(module, export_name)
    return module


def __getattr__(name: str) -> Any:
    if name not in _FUZZ_EXPORT_SET:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = _load_fuzz_harness()
    if name == "fuzz_harness":
        return module
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | _FUZZ_EXPORT_SET)


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
    "FuzzResult",
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
    "assert_no_crashes",
    "assert_no_timeouts",
    "collect_corpus_inputs",
    "constants",
    "create_parser",
    "describe_parse_error",
    "fuzz_parse_text",
    "generate_random_text",
    "is_compressed",
    "iter_child_nodes",
    "parse_and_validate",
    "parse_graphics_file",
    "parse_graphics_text",
    "parse_source_file",
    "parse_source_text",
    "preprocess_sl_text",
    "preprocess_source",
    "render_ide_text",
    "resolve_graphics_companion_path",
    "run_corpus_regression",
    "run_random_fuzz",
    "validate_basepicture",
    "walk",
]
