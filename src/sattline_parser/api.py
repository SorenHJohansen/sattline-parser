"""Public parser-core entry points and orchestration layer.

This module owns the public API, the Lark parser cache, and the parse
pipeline. Lower-level error formatting lives in :mod:`sattline_parser.errors`
and source pre-processing lives in :mod:`sattline_parser.preprocessing`.
"""

from __future__ import annotations

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
    _render_source_context as _render_source_context,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .errors import (
    _rewrite_summary_location as _rewrite_summary_location,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .errors import (
    _unexpected_input_summary as _unexpected_input_summary,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .grammar import constants as const
from .preprocessing import is_compressed, preprocess_sl_text
from .preprocessing.comments import strip_sl_comments, strip_sl_comments_with_mapping

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
    "strip_sl_comments",
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
def _formatted_grammar() -> str:
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
    strict: bool,
) -> str:
    cache_key = sha256()
    cache_key.update(_formatted_grammar().encode("utf-8"))
    cache_key.update(start.encode("utf-8"))
    cache_key.update(str(propagate_positions).encode("ascii"))
    cache_key.update(str(strict).encode("ascii"))
    cache_key.update(lark_version.encode("utf-8"))
    _PARSER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return str(_PARSER_CACHE_DIR / f"{cache_key.hexdigest()}.lark")


def build_lark_parser(
    *,
    start: str = "start",
    propagate_positions: bool = True,
    strict: bool = False,
) -> Lark:
    return Lark(
        _formatted_grammar(),
        start=start,
        parser="lalr",
        propagate_positions=propagate_positions,
        strict=strict,
        regex=True,
        cache=_parser_cache_path(
            start=start,
            propagate_positions=propagate_positions,
            strict=strict,
        ),
        cache_grammar=True,
    )


def create_parser(*, strict: bool = False) -> Lark:
    """Load and compile the SattLine grammar."""
    return build_lark_parser(strict=strict)


def create_sl_parser(*, strict: bool = False) -> Lark:
    """Compatibility alias for create_parser."""
    return create_parser(strict=strict)


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
    if not is_compressed(src):
        return src
    if debug is not None:
        debug("Compressed format detected; decoding before parsing")
    try:
        src, _ = preprocess_sl_text(src)
    except Exception as exc:
        if log_failures:
            _log_parser_failure(stage="decode", exc=exc, source_text=src, source_path=source_path)
        raise
    return src


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
    decoded = _decode_compressed_source(
        src,
        debug=debug,
        source_path=source_path,
        log_failures=log_failures,
    )
    stripped = strip_sl_comments_with_mapping(decoded)
    cleaned = stripped.text
    active_parser = parser if parser is not None else _default_parser()
    active_transformer = transformer if transformer is not None else SLTransformer()
    parser_runner = cast(_ParserProtocol, active_parser)
    try:
        tree = parser_runner.parse(cleaned)
    except Exception as exc:
        if log_failures:
            _log_parser_failure(stage="parse", exc=exc, source_text=src, source_path=source_path)
        raise

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
    src = load_source_text(code_path, debug=debug)
    return parse_source_text(
        src,
        parser=parser,
        transformer=transformer,
        debug=debug,
        source_path=code_path,
        log_failures=log_failures,
    )
