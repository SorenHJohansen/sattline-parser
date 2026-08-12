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
from lark.lexer import ContextualLexer

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
    _unexpected_input_summary as _unexpected_input_summary,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .grammar import constants as const
from .grammar.sattline_lexer import SattLineLexer
from .preprocessing import is_compressed, preprocess_sl_text

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
def _formatted_grammar() -> str:
    grammar_text = GRAMMAR_PATH.read_text(encoding="utf-8")
    grammar_substitutions = {
        name: getattr(const, name)
        for name in dir(const)
        if name.startswith("GRAMMAR_VALUE_") or name.startswith("GRAMMAR_REGEX_")
    }
    return grammar_text.format(**grammar_substitutions)


#: Comments are structurally exposed in the default grammar, which makes the
#: LALR table carry inherent Shift/Reduce ambiguities at construct boundaries
#: (a comment may trail the inner construct or start the enclosing repetition).
#: Strict mode therefore validates the core, comment-free grammar instead.
_COMMENT_RULE_PREFIXES = (
    "comment:",
    "?comment_content:",
    "comments:",
    "code_comment:",
    "comment_stmt:",
    "change_description:",
    "module_description_comment:",
    "module_typedescription:",
    "module_end_comment:",
)
_COMMENT_TERMINAL_PREFIXES = ("COMMENT_START:", "COMMENT_END:", "COMMENT_TEXT:")


@lru_cache(maxsize=1)
def _core_grammar() -> str:
    """The comment-free grammar used by strict-mode builds."""
    lines = _formatted_grammar().splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(prefix) for prefix in _COMMENT_RULE_PREFIXES):
            continue
        if any(stripped.startswith(prefix) for prefix in _COMMENT_TERMINAL_PREFIXES):
            continue
        kept.append(line)
    text = "\n".join(kept)
    # Longest role-tagged rules first to avoid partial-match corruption.
    return (
        text.replace("code_comment | ", "")
        .replace("comments | ", "")
        .replace("comments? ", "")
        .replace("comments? ,", "")
        .replace("comments?", "")
        .replace("change_description? ", "")
        .replace("change_description?", "")
        .replace("module_description_comment? ", "")
        .replace("module_description_comment?", "")
        .replace("module_typedescription? ", "")
        .replace("module_typedescription?", "")
        .replace(" module_end_comment? ", " ")
        .replace(" module_end_comment?", "")
        .replace(" module_end_comment ", " ")
        .replace("| comment_stmt", "")
    )


def _parser_cache_path(
    *,
    start: str,
    propagate_positions: bool,
    strict: bool,
) -> str:
    cache_key = sha256()
    grammar_text = _core_grammar() if strict else _formatted_grammar()
    cache_key.update(grammar_text.encode("utf-8"))
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
    plugins: dict[str, type[ContextualLexer]] = {}
    if not strict:
        plugins["ContextualLexer"] = SattLineLexer
    return Lark(
        _core_grammar() if strict else _formatted_grammar(),
        start=start,
        parser="lalr",
        lexer="contextual",
        propagate_positions=propagate_positions,
        strict=strict,
        regex=True,
        cache=_parser_cache_path(
            start=start,
            propagate_positions=propagate_positions,
            strict=strict,
        ),
        cache_grammar=True,
        _plugins=plugins,
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
    active_parser = parser if parser is not None else _default_parser()
    active_transformer = transformer if transformer is not None else SLTransformer()
    parser_runner = cast(_ParserProtocol, active_parser)
    try:
        tree = parser_runner.parse(decoded)
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
