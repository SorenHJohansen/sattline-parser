"""Public parser-core entry points and orchestration layer.

This module owns the public API, the Lark parser cache, and the parse
pipeline. Lower-level error formatting lives in :mod:`sattline_parser.errors`
and source pre-processing lives in :mod:`sattline_parser.preprocessing`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir
from typing import Protocol, cast

from lark import Lark, Token, Tree
from lark import __version__ as lark_version
from lark.exceptions import UnexpectedInput

from sattline_parser.models.ast_model import BasePicture
from sattline_parser.source_document import remap_parse_error, remap_tree_to_original
from sattline_parser.transformer.sl_transformer import SLTransformer

from .errors import (
    ParseErrorDetails,
    _log_parser_failure,  # pyright: ignore[reportPrivateUsage]  # imported for internal use
    describe_parse_error,
)
from .errors import (
    _failure_details as _failure_details,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .errors import (
    _unexpected_input_summary as _unexpected_input_summary,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .grammar import constants as const
from .grammar.sattline_lexer import SattLineLexer
from .preprocessing import is_compressed, preprocess_source

__all__ = [
    "ParseErrorDetails",
    "build_lark_parser",
    "create_parser",
    "create_sl_parser",
    "describe_parse_error",
    "load_source_text",
    "parse_source_file",
    "parse_source_text",
    "read_text_with_fallback",
]

GRAMMAR_PATH = Path(__file__).resolve().parent / "grammar" / "sattline.lark"
_PARSER_CACHE_DIR = Path(gettempdir()) / "sattline-parser" / "lark-cache"

if not GRAMMAR_PATH.exists():
    raise RuntimeError(f"Grammar file missing: {GRAMMAR_PATH}")


class _ParserProtocol(Protocol):
    def parse(
        self,
        text: str,
        start: str | None = None,
        _on_error: Callable[[UnexpectedInput], bool] | None = None,
    ) -> Tree[Token]: ...


@lru_cache(maxsize=1)
def _resolved_grammar() -> str:
    """Return the single authoritative SattLine grammar with constants applied.

    ``sattline.lark`` is the canonical grammar; it is a template whose
    ``{GRAMMAR_VALUE_*}`` / ``{GRAMMAR_REGEX_*}`` placeholders are filled from
    :mod:`sattline_parser.grammar.constants` so the terminal spellings live in
    exactly one place. No grammar is generated or manipulated beyond this
    substitution: comments are explicit grammar elements in ``sattline.lark``
    and are legal exactly where the grammar places them.
    """
    grammar_text = GRAMMAR_PATH.read_text(encoding="utf-8")
    grammar_substitutions = {
        name: getattr(const, name)
        for name in dir(const)
        if name.startswith("GRAMMAR_VALUE_") or name.startswith("GRAMMAR_REGEX_")
    }
    return grammar_text.format(**grammar_substitutions)


def _parser_cache_path(
    *,
    start: str,
    propagate_positions: bool,
) -> str:
    cache_key = sha256()
    cache_key.update(_resolved_grammar().encode("utf-8"))
    cache_key.update(start.encode("utf-8"))
    cache_key.update(str(propagate_positions).encode("ascii"))
    cache_key.update(lark_version.encode("utf-8"))
    # Lark's own cache payload already includes sys.version_info[:2]; include it
    # in the filename too so a cache written by another interpreter is never read.
    cache_key.update(f"py-{sys.version_info[0]}.{sys.version_info[1]}".encode("ascii"))
    _PARSER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return str(_PARSER_CACHE_DIR / f"{cache_key.hexdigest()}.lark")


def build_lark_parser(
    *,
    start: str = "start",
    propagate_positions: bool = True,
) -> Lark:
    """Load and compile the single authoritative SattLine grammar.

    Every build uses :func:`_resolved_grammar` (comments legal exactly where
    ``sattline.lark`` places them) and the :class:`SattLineLexer` (structural,
    context-aware ``(* ... *)`` comment handling).
    """
    return Lark(
        _resolved_grammar(),
        start=start,
        parser="lalr",
        lexer="contextual",
        propagate_positions=propagate_positions,
        regex=True,
        cache=_parser_cache_path(start=start, propagate_positions=propagate_positions),
        cache_grammar=True,
        _plugins={"ContextualLexer": SattLineLexer},
    )


def create_parser() -> Lark:
    """Load and compile the SattLine grammar."""
    return build_lark_parser()


def create_sl_parser() -> Lark:
    """Compatibility alias for :func:`create_parser`."""
    return create_parser()


@lru_cache(maxsize=1)
def _default_parser() -> Lark:
    return create_parser()


def _decode_compressed_source(
    src: str,
    *,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
) -> str:
    """Decode compressed *src*, returning the decoded text (no provenance).

    ``parse_source_text`` uses :func:`preprocess_source` instead so that
    original-source provenance is preserved; this helper exists for
    :func:`load_source_text` callers that only need the decoded text.
    """
    if not is_compressed(src):
        return src
    if debug is not None:
        debug("Compressed format detected; decoding before parsing")
    try:
        return preprocess_source(src).normalized_text
    except Exception as exc:
        if log_failures:
            _log_parser_failure(stage="decode", exc=exc, source_text=src, source_path=source_path)
        raise


def read_text_with_fallback(path: Path) -> str:
    """Read a text file trying utf-8, then cp1252, then latin-1."""
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            _log_parser_failure(stage="read", exc=exc, source_path=path)
            raise
    return path.read_text(encoding="latin-1")


# Internal alias kept for callers that import the private name.
_read_text_simple = read_text_with_fallback


def load_source_text(
    code_path: Path,
    *,
    debug: Callable[[str], None] | None = None,
) -> str:
    source_path = Path(code_path)
    if debug is not None:
        debug(f"Parsing file: {source_path}")

    src = _read_text_simple(source_path)
    return _decode_compressed_source(src, debug=debug, source_path=source_path)


def parse_source_text(
    src: str,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
) -> BasePicture:
    try:
        source_doc = preprocess_source(src)
    except Exception as exc:
        if log_failures:
            _log_parser_failure(stage="decode", exc=exc, source_text=src, source_path=source_path)
        raise
    if debug is not None and not source_doc.is_identity():
        debug("Compressed format detected; decoding before parsing")

    active_parser = parser if parser is not None else _default_parser()
    active_transformer = transformer if transformer is not None else SLTransformer()
    parser_runner = cast(_ParserProtocol, active_parser)
    try:
        tree = parser_runner.parse(source_doc.normalized_text)
    except Exception as exc:
        remap_parse_error(exc, source_doc)
        if log_failures:
            _log_parser_failure(
                stage="parse",
                exc=exc,
                source_text=src,
                source_path=source_path,
                source_document=source_doc,
            )
        raise

    # Rewrite every AST-visible position from normalized to original coordinates.
    remap_tree_to_original(tree, source_doc)

    if debug is not None:
        debug("Parse OK, transforming with SLTransformer")

    try:
        transformed = active_transformer.transform(tree)
        if not isinstance(transformed, BasePicture):
            raise RuntimeError("Transform result is not BasePicture; check transformer.start()")
    except Exception as exc:
        if log_failures:
            _log_parser_failure(stage="transform", exc=exc, source_text=src, source_path=source_path)
        raise

    basepic = transformed
    try:
        basepic.parse_tree = tree
    except AttributeError:
        if debug is not None:
            debug("BasePicture does not allow dynamic attributes; parse tree not attached")

    if debug is not None:
        debug(f"Transform result type: {type(basepic).__name__}")

    return basepic


def parse_source_file(
    code_path: Path,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    log_failures: bool = True,
) -> BasePicture:
    source_path = Path(code_path)
    if debug is not None:
        debug(f"Parsing file: {source_path}")
    # Read the raw file (with encoding fallback) and hand the original text to
    # parse_source_text so compression/decoding and source provenance happen
    # exactly once and consistently with parse_source_text().
    raw = _read_text_simple(source_path)
    return parse_source_text(
        raw,
        parser=parser,
        transformer=transformer,
        debug=debug,
        source_path=source_path,
        log_failures=log_failures,
    )
