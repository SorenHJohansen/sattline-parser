"""JSON helpers: a versioned document envelope and an AST serialiser."""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import Path
from typing import cast

from sattline_parser.models.ast_model import SourceSpan

__all__ = ["SCHEMA_PREFIX", "dumps", "to_jsonable"]

#: Every payload the CLI emits is tagged with a versioned schema id.
SCHEMA_PREFIX = "sattline.v1"

#: Fields never serialised: the retained Lark tree is tooling state, not the AST.
_SKIPPED_FIELDS = frozenset({"parse_tree"})


def to_jsonable(value: object, *, depth: int) -> object:
    """Convert AST values into JSON-friendly data, stopping at ``depth``.

    Scalars, enums, paths and source spans are emitted in full; dataclasses and
    containers recurse and decrement the remaining depth, so ``--depth`` bounds
    the output. At the limit a composite value is replaced by a placeholder such
    as ``<ModuleDef>`` or ``<12 items>`` rather than silently disappearing.
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if depth <= 0:
        return _placeholder(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, SourceSpan):
        return _span(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list | tuple):
        items = cast("list[object] | tuple[object, ...]", value)
        return [to_jsonable(item, depth=depth - 1) for item in items]
    if isinstance(value, dict):
        pairs = cast("dict[object, object]", value)
        mapping = {str(key): to_jsonable(item, depth=depth - 1) for key, item in pairs.items()}
        return mapping
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name), depth=depth - 1)
            for field in dataclasses.fields(value)
            if field.name not in _SKIPPED_FIELDS
        }
    return repr(value)[:200]


def _span(span: SourceSpan) -> dict[str, object]:
    return {"start": span.start, "end": span.end, "line": span.line, "column": span.column}


def _placeholder(value: object) -> str:
    if isinstance(value, list | tuple):
        items = cast("list[object] | tuple[object, ...]", value)
        return f"<{len(items)} items>"
    if isinstance(value, dict):
        pairs = cast("dict[object, object]", value)
        return f"<{len(pairs)} keys>"
    return f"<{type(value).__name__}>"


def dumps(payload: object, *, compact: bool = False) -> str:
    """Serialise a payload; ``compact`` emits one line."""
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False, indent=2)
