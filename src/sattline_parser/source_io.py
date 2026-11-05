"""Source decoding and the parse pipeline (below the public façade).

This module owns the Lark parser cache and the source-to-``BasePicture``
pipeline. It deliberately imports neither :mod:`sattline_parser.api` nor
:mod:`sattline_parser.project` so both can build on it: the project layer
loads files through it, and the public ``api`` façade re-exports it.
"""

from __future__ import annotations

import dataclasses
import getpass
import os
import sys
from collections.abc import Callable, Iterator
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir
from typing import NoReturn, Protocol, cast

from lark import Lark, Token, Tree
from lark import __version__ as lark_version
from lark.exceptions import VisitError

from sattline_parser.models.ast_model import BasePicture
from sattline_parser.source_document import remap_parse_error, remap_tree_to_original
from sattline_parser.transformer.sl_transformer import SLTransformer
from sattline_parser.validation import Diagnostic, validate_basepicture

from .errors import (
    ParseErrorDetails,
    SourceTooDeepError,
    _log_parser_failure,  # pyright: ignore[reportPrivateUsage]  # imported for internal use
    describe_parse_error,
)
from .grammar.resolved import grammar_fingerprint
from .grammar.resolved import resolved_grammar as _resolved_grammar
from .grammar.sattline_lexer import SattLineLexer, compact_provenance
from .preprocessing import is_coded, is_compressed, preprocess_source, render_ide_text
from .preprocessing.coded import decode_coded_stream
from .preprocessing.compressed import scan_opaque_regions

__all__ = [
    "MAX_SOURCE_DEPTH",
    "ParseErrorDetails",
    "SourceTooDeepError",
    "build_lark_parser",
    "create_parser",
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

_CACHE_DIR_MODE = 0o700
_CACHE_DIR_NAME = "sattline-parser"

#: Maximum number of structural levels accepted from one source.
#:
#: ``walk`` is iterative, but validation type inference, the formatter,
#: dataclass ``repr``/``eq`` and the pickle-based AST cache still recurse.
#: The check follows every dataclass field, container, and raw grammar tree,
#: so property payloads such as interactor tails are covered too. A 256-level
#: structure keeps the recursive consumers inside CPython's default recursion
#: limit while staying far above any hand-written SattLine expression.
MAX_SOURCE_DEPTH = 256


def _structure_children(value: object) -> Iterator[object]:
    """Yield the values that a recursive consumer would descend into."""
    if isinstance(value, Tree):
        yield from cast(Tree[object], value).children
    elif isinstance(value, dict):
        yield from value.values()
    elif isinstance(value, list | tuple | set | frozenset):
        yield from value
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for structure_field in dataclasses.fields(value):
            yield getattr(value, structure_field.name)


def _first_too_deep_structure(root: object, limit: int) -> object | None:
    """Return the first value deeper than *limit*, or ``None``.

    The traversal is iterative, so the check itself cannot raise
    ``RecursionError``. It stops at the first offending value: the exact depth
    beyond the limit and the rest of the structure do not change the
    diagnostic.
    """
    stack: list[tuple[object, int]] = [(root, 1)]
    seen: dict[int, int] = {}
    while stack:
        current, depth = stack.pop()
        if depth > limit:
            return current
        identity = id(current)
        if seen.get(identity, 0) >= depth:
            continue
        seen[identity] = depth
        children = [
            child
            for child in _structure_children(current)
            if not isinstance(child, bool | int | float | str | bytes) and child is not None
        ]
        for child in reversed(children):
            stack.append((child, depth + 1))
    return None


def _source_too_deep_error(node: object | None = None) -> SourceTooDeepError:
    """Build the clean parse failure for an over-deep structure."""
    line: int | None = None
    column: int | None = None
    pos_in_stream: int | None = None
    if node is not None:
        span = getattr(node, "span", None)
        line_value = getattr(span, "line", None)
        column_value = getattr(span, "column", None)
        start_value = getattr(span, "start", None)
        if isinstance(line_value, int):
            line = line_value
        if isinstance(column_value, int):
            column = column_value
        if isinstance(start_value, int):
            pos_in_stream = start_value
    error = SourceTooDeepError(
        MAX_SOURCE_DEPTH,
        line=line,
        column=column,
        pos_in_stream=pos_in_stream,
    )
    if pos_in_stream is not None:
        # AST spans are already in original coordinates; remapping again would
        # shift a second time.
        error._sattline_remapped = True  # type: ignore[attr-defined]
    return error


# ``os.getuid`` is POSIX-only. Resolving it once keeps the platform probe out of
# the hot path and lets the tests drive both cases on any platform.
_getuid: Callable[[], int] | None = getattr(os, "getuid", None)


def _cache_owner_token() -> str:
    """A per-user token for the cache directory name."""
    if _getuid is None:
        return getpass.getuser()
    return str(_getuid())


def _private_cache_dir(path: Path) -> Path | None:
    """Create ``path`` as a private directory, or return ``None``.

    The directory is created with mode ``0700`` and reused only when it belongs
    to this user and no group or world bits are set. Anything else (a read-only
    temp directory, a directory planted by another user) disables the cache.
    """
    try:
        path.mkdir(mode=_CACHE_DIR_MODE, parents=True, exist_ok=True)
        info = path.stat()
        if _getuid is not None and info.st_uid != _getuid():
            return None
        if info.st_mode & 0o077:
            path.chmod(_CACHE_DIR_MODE)
    except OSError:
        return None
    return path


def _parser_cache_dir() -> Path | None:
    """The per-user Lark cache directory, or ``None`` when it cannot be private.

    Lark's parser cache is a pickle, so it must not live in a directory another
    user of the machine can write to. Each user gets a directory named after
    their uid, created ``0700``, and a directory that fails the ownership or
    permission check disables the cache entirely.
    """
    directory = Path(gettempdir()) / f"{_CACHE_DIR_NAME}-{_cache_owner_token()}" / "lark-cache"
    return _private_cache_dir(directory)


class _ParserProtocol(Protocol):
    """The slice of Lark's parser interface the pipeline calls."""

    def parse(self, text: str) -> Tree[Token]: ...


def _parser_cache_path(
    *,
    start: str,
    propagate_positions: bool,
) -> str | None:
    """The cache file for this grammar and parser shape, or ``None`` if disabled."""
    cache_key = sha256()
    cache_key.update(grammar_fingerprint().encode("ascii"))
    cache_key.update(start.encode("utf-8"))
    cache_key.update(str(propagate_positions).encode("ascii"))
    cache_key.update(lark_version.encode("utf-8"))
    # Lark's own cache payload already includes sys.version_info[:2]; include it
    # in the filename too so a cache written by another interpreter is never read.
    cache_key.update(f"py-{sys.version_info[0]}.{sys.version_info[1]}".encode("ascii"))
    directory = _parser_cache_dir()
    if directory is None:
        return None
    return str(directory / f"{cache_key.hexdigest()}.lark")


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
        # Lark's contextual-lexer plugin hook is private. The `<1.4` pin plus the
        # "Lark Compatibility" CI job that builds against the newest 1.3.x is what
        # keeps that dependency explicit instead of silently drifting.
        _plugins={"ContextualLexer": SattLineLexer},
    )


def create_parser() -> Lark:
    """Load and compile the SattLine grammar."""
    return build_lark_parser()


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


_UNDEFINED_LOW = "\udc80"
_UNDEFINED_HIGH = "\udcff"


def _decode_cp1252_comments_tolerant(raw: bytes) -> str:
    """Decode Windows-1252, tolerating undefined bytes **inside comments only**.

    The byte ``0x81`` is undefined in Windows-1252, yet a file is accepted when
    that byte sits inside a ``(* ... *)`` comment. So an undefined byte in a
    comment body is legal and must not fail the decode. Inside a comment body such a byte decodes to
    ``U+FFFD``; there is no encoding that maps it to a real character.

    Everywhere else the decode stays strict, and nothing is ever re-read as utf-8
    or latin-1. The scan reuses :func:`scan_opaque_regions`, so it follows the
    same lexical rules as the rest of the pipeline: comment bodies nest, and a
    ``(*`` or ``*)`` inside a string literal is text, not a delimiter.

    An unterminated comment or string is not tolerated: there is no reliable
    boundary for it, so the strict decode error survives.
    """
    # surrogateescape never fails and maps one byte to one character, so a lone
    # surrogate marks exactly one undefined byte and keeps offsets aligned.
    text = raw.decode("cp1252", errors="surrogateescape")
    if not any(_UNDEFINED_LOW <= character <= _UNDEFINED_HIGH for character in text):
        return text

    comment_spans = [
        (start, end) for kind, start, end in scan_opaque_regions(text) if kind == "C" and text.endswith("*)", 0, end)
    ]
    characters = list(text)
    span_index = 0
    for index, character in enumerate(characters):
        if not (_UNDEFINED_LOW <= character <= _UNDEFINED_HIGH):
            continue
        while span_index < len(comment_spans) and comment_spans[span_index][1] <= index:
            span_index += 1
        if span_index >= len(comment_spans) or comment_spans[span_index][0] > index:
            raise UnicodeDecodeError("cp1252", raw, index, index + 1, "character maps to <undefined>")
        characters[index] = "\ufffd"
    return "".join(characters)


def _decode_source_bytes_for_parse(path: Path) -> str:
    """Read a source file for the parse path, allowing undefined comment bytes."""
    try:
        return read_text_cp1252(path)
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
    comments only.
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
    """Read a source file and return the decoded plain text.

    This is the read-then-decode helper for callers that want the final text
    rather than a parse result: byte-coded streams and marker-compressed text
    both come back decoded, and undefined Windows-1252 bytes are tolerated
    inside comments. :func:`source_text_for_parse` differs on purpose: it
    leaves marker-compressed text as written so provenance spans keep pointing
    into the original source.
    """
    source_path = Path(code_path)
    if debug is not None:
        debug(f"Parsing file: {source_path}")

    raw_bytes = source_path.read_bytes()
    if is_coded(raw_bytes):
        return _decode_coded_file_bytes(raw_bytes, debug=debug, source_path=source_path)
    src = _decode_source_bytes_for_parse(source_path)
    return _decode_compressed_source(src, debug=debug, source_path=source_path)


def _recursion_cause(exc: Exception) -> RecursionError | None:
    """Return the recursion overflow behind *exc*, including a Lark wrapper."""
    if isinstance(exc, RecursionError):
        return exc
    if isinstance(exc, VisitError) and isinstance(exc.orig_exc, RecursionError):
        return exc.orig_exc
    return None


def _raise_source_too_deep(
    stage: str,
    exc: RecursionError,
    *,
    src: str,
    source_path: Path | None,
    log_failures: bool,
) -> NoReturn:
    """Convert a recursive-stage overflow into the ordinary nesting failure."""
    deep_error = _source_too_deep_error()
    if log_failures:
        _log_parser_failure(stage=stage, exc=deep_error, source_text=src, source_path=source_path)
    raise deep_error from exc


def _reject_too_deep_structure(
    root: BasePicture,
    *,
    src: str,
    source_path: Path | None,
    log_failures: bool,
) -> None:
    """Raise :class:`SourceTooDeepError` when *root* exceeds the depth limit."""
    too_deep = _first_too_deep_structure(root, MAX_SOURCE_DEPTH)
    if too_deep is None:
        return
    deep_error = _source_too_deep_error(too_deep)
    if log_failures:
        _log_parser_failure(stage="depth", exc=deep_error, source_text=src, source_path=source_path)
    raise deep_error


def parse_source_text(
    src: str,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
) -> BasePicture:
    """Parse SattLine source text and transform it into a :class:`BasePicture`.

    The pipeline is preprocess, parse, remap, transform:

    * ``src`` is preprocessed first. A marker-compressed source is decoded into
      normalized text while the original text is kept for provenance.
    * The parse tree is produced from the normalized text. Parse errors are
      remapped from normalized coordinates back to the original source before
      they propagate, so ``line``/``column`` describe what the caller wrote.
    * When the source was decoded, AST positions are rewritten to original
      coordinates, so spans always point into ``src`` as given.
    * The tree is handed to an :class:`SLTransformer`, which must return a
      :class:`BasePicture`.
    * A result whose AST exceeds :data:`MAX_SOURCE_DEPTH` levels is rejected
      with :class:`SourceTooDeepError` rather than allowed to reach a
      recursively implemented consumer.

    ``parser`` and ``transformer`` default to a shared cached parser and a fresh
    transformer. ``debug`` receives progress messages. ``source_path`` is only
    used to label logged failures, and ``log_failures`` (default on) logs each
    stage failure with its source location before the exception propagates.

    This is a pure parse and transform entry point. Use
    :func:`parse_and_validate` to also run strict single-source validation.
    """
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
    except RecursionError as exc:
        # A custom parser or an unusually low interpreter recursion limit can
        # still overflow. Report it as invalid input, never as a parser crash.
        _raise_source_too_deep("parse", exc, src=src, source_path=source_path, log_failures=log_failures)
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
    try:
        remap_tree_to_original(tree, source_doc)
    except RecursionError as exc:
        _raise_source_too_deep("remap", exc, src=src, source_path=source_path, log_failures=log_failures)

    if debug is not None:
        debug("Parse OK, transforming with SLTransformer")

    try:
        transformed = active_transformer.transform(tree)
        if not isinstance(transformed, BasePicture):
            raise RuntimeError("Transform result is not BasePicture; check transformer.start()")
    except Exception as exc:
        recursion = _recursion_cause(exc)
        if recursion is not None:
            _raise_source_too_deep("transform", recursion, src=src, source_path=source_path, log_failures=log_failures)
        if log_failures:
            _log_parser_failure(stage="transform", exc=exc, source_text=src, source_path=source_path)
        raise

    _reject_too_deep_structure(transformed, src=src, source_path=source_path, log_failures=log_failures)

    if debug is not None:
        debug(f"Transform result type: {type(transformed).__name__}")

    return transformed


def parse_and_validate(
    src: str,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
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
    )
    return basepic, validate_basepicture(basepic)


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
    )
