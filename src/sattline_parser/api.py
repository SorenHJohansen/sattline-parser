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
from sattline_parser.validation import Diagnostic, validate_basepicture

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
from .grammar.keywords import make_keywords_case_insensitive
from .grammar.sattline_lexer import SattLineLexer, compact_provenance
from .preprocessing import is_coded, is_compressed, preprocess_source, render_ide_text
from .preprocessing.coded import decode_coded_stream

__all__ = [
    "ParseErrorDetails",
    "build_lark_parser",
    "create_parser",
    "create_sl_parser",
    "decode_source_bytes",
    "describe_parse_error",
    "load_source_text",
    "parse_and_validate",
    "parse_source_file",
    "parse_source_text",
    "read_text_cp1252",
    "render_ide_text",
    "source_text_for_parse",
    "validate_basepicture",
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
    return make_keywords_case_insensitive(grammar_text.format(**grammar_substitutions))


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


def _decode_coded_file_bytes(
    raw_bytes: bytes,
    *,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
) -> str:
    """Decode the binary framing of a coded SattLine file (no provenance)."""
    if not is_coded(raw_bytes):
        raise ValueError("not a coded stream")
    if debug is not None:
        debug("Coded format detected; decoding binary stream")
    try:
        return decode_coded_stream(raw_bytes)
    except Exception as exc:
        if log_failures:
            _log_parser_failure(stage="decode", exc=exc, source_path=source_path)
        raise


def read_text_cp1252(path: Path) -> str:
    """Read a SattLine source file as **Windows-1252** (cp1252) text.

    Windows-1252 is the only encoding the real SattLine parser accepts, so this
    is a strict decode with **no encoding fallback**: a file whose bytes are
    not valid Windows-1252 (the undefined bytes ``0x81 0x8D 0x8F 0x90 0x9D``)
    raises :class:`UnicodeDecodeError` rather than being silently re-read as
    utf-8 or latin-1, which would decode a mis-encoded file into plausible but
    wrong text instead of reporting the problem.

    Reads in binary mode to preserve original line endings (CRLF). Python's
    ``path.read_text()`` performs universal newline translation which would
    silently convert CRLF to LF.
    """
    return path.read_bytes().decode("cp1252")


# Internal alias kept for callers that import the private name.
_read_text_simple = read_text_cp1252


def _decode_cp1252_comments_tolerant(raw: bytes) -> str:
    """Decode Windows-1252, tolerating undefined bytes **inside comments only**.

    Proved 2026-10-05 by ``HighByteInvalid.x``: the byte ``0x81`` is undefined in
    Windows-1252, yet the real editor compiles the file because the byte sits
    inside a ``(* ... *)`` comment. So an undefined byte in a comment body is
    legal and must not fail the decode.

    Everywhere else the decode stays strict. Code, string literals and the
    undefined bytes themselves are unchanged, so ``b"\\x81A"`` still raises
    :class:`UnicodeDecodeError` exactly as before - this only widens what is
    accepted inside a comment body, and never re-reads anything as utf-8 or
    latin-1.

    Comment scanning is deliberately naive (no nesting, no string awareness).
    That errs toward the previous strict behaviour: an unrecognised comment
    region simply fails to decode as it did before, rather than silently
    accepting bad code.
    """
    # Fast path: a file that decodes strictly needs no scanning at all.
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        pass

    parts: list[str] = []
    pos = 0
    while True:
        start = raw.find(b"(*", pos)
        if start < 0:
            parts.append(raw[pos:].decode("cp1252"))
            break
        parts.append(raw[pos:start].decode("cp1252"))
        end = raw.find(b"*)", start + 2)
        if end < 0:
            # Unterminated comment: the lexer would reject this anyway, so keep
            # the strict behaviour rather than guessing where the comment ends.
            # The tail still decodes strictly, so undefined bytes raise here.
            return "".join(parts) + raw[start:].decode("cp1252")
        parts.append(raw[start : end + 2].decode("cp1252", errors="replace"))
        pos = end + 2
    return "".join(parts)


def _decode_source_bytes_for_parse(path: Path) -> str:
    """Read a source file for the parse path, allowing undefined comment bytes."""
    try:
        return _read_text_simple(path)
    except UnicodeDecodeError:
        return _decode_cp1252_comments_tolerant(path.read_bytes())


def decode_source_bytes(
    raw_bytes: bytes,
    *,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
) -> str:
    """Decode raw source bytes into the text :func:`parse_source_text` expects.

    Byte-coded streams (the binary ``\\x80 3.1`` framing some ``.x`` files
    carry) are decoded first. Everything else is returned as written —
    including marker-compressed text, so provenance spans keep pointing into
    the original source. Undefined Windows-1252 bytes are tolerated inside
    comments only, exactly as the real editor accepts them.
    """
    if is_coded(raw_bytes):
        return _decode_coded_file_bytes(raw_bytes, debug=debug, source_path=source_path, log_failures=log_failures)
    try:
        return raw_bytes.decode("cp1252")
    except UnicodeDecodeError:
        return _decode_cp1252_comments_tolerant(raw_bytes)


def source_text_for_parse(
    code_path: Path,
    *,
    debug: Callable[[str], None] | None = None,
    log_failures: bool = True,
) -> str:
    """Read a source file into the text :func:`parse_source_file` parses.

    Handles the three on-disk flavors the editor produces: byte-coded streams,
    marker-compressed text and plain Windows-1252 text.
    """
    source_path = Path(code_path)
    return decode_source_bytes(
        source_path.read_bytes(),
        debug=debug,
        source_path=source_path,
        log_failures=log_failures,
    )


def load_source_text(
    code_path: Path,
    *,
    debug: Callable[[str], None] | None = None,
) -> str:
    source_path = Path(code_path)
    if debug is not None:
        debug(f"Parsing file: {source_path}")

    raw_bytes = source_path.read_bytes()
    if is_coded(raw_bytes):
        return _decode_coded_file_bytes(raw_bytes, debug=debug, source_path=source_path)
    src = _decode_source_bytes_for_parse(source_path)
    return _decode_compressed_source(src, debug=debug, source_path=source_path)


def parse_source_text(
    src: str,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
    retain_parse_tree: bool = False,
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
    provenance = None if source_doc.is_identity() else source_doc.is_decoded_range
    try:
        with compact_provenance(provenance):
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
    if retain_parse_tree:
        try:
            basepic.parse_tree = tree
        except AttributeError:
            if debug is not None:
                debug("BasePicture does not allow dynamic attributes; parse tree not attached")

    if debug is not None:
        debug(f"Transform result type: {type(basepic).__name__}")

    return basepic


def parse_and_validate(
    src: str,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
    retain_parse_tree: bool = False,
) -> tuple[BasePicture, tuple[Diagnostic, ...]]:
    """Parse a SattLine source and run strict single-source validation.

    Returns ``(basepicture, diagnostics)``; ``diagnostics`` is empty for a
    source that fully validates. ``parse_source_text`` itself stays a pure
    parse/transform pipeline — callers opt into validation by using this entry
    point.
    """
    basepic = parse_source_text(
        src,
        parser=parser,
        transformer=transformer,
        debug=debug,
        source_path=source_path,
        log_failures=log_failures,
        retain_parse_tree=retain_parse_tree,
    )
    return basepic, validate_basepicture(basepic)


def parse_source_file(
    code_path: Path,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    log_failures: bool = True,
    retain_parse_tree: bool = False,
) -> BasePicture:
    source_path = Path(code_path)
    if debug is not None:
        debug(f"Parsing file: {source_path}")
    # Read the raw file (byte-coded, compressed or strict Windows-1252) and hand
    # the resulting text to parse_source_text so compression/decoding and source
    # provenance happen exactly once and consistently with parse_source_text().
    raw = source_text_for_parse(source_path, debug=debug, log_failures=log_failures)
    return parse_source_text(
        raw,
        parser=parser,
        transformer=transformer,
        debug=debug,
        source_path=source_path,
        log_failures=log_failures,
        retain_parse_tree=retain_parse_tree,
    )
