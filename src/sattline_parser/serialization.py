"""Serialise the AST and the project model as JSON-friendly data.

``to_jsonable`` turns a :class:`~sattline_parser.ast.BasePicture`, a program, a
diagnostic, or any other model value into plain Python values that
:func:`json.dumps` accepts. ``to_json`` does the JSON encoding in one step. The
conversion is deliberately structural: every dataclass field is emitted under
its own name, so the shape follows the model rather than a hand-written
projection, and a new field appears without a serializer change.

The output is a data view, not a supported file format. Field names follow the
model and change with it; the documented JSON schemas under ``docs/cli.md`` are
the stable contract for the CLI, not this module.

Traversal stops at a ``depth`` limit. A composite value at the limit is replaced
by a placeholder such as ``"<ModuleDef>"`` or ``"<12 items>"`` instead of
disappearing, so a truncated payload still shows what was there. The default is
unlimited, which is what a consumer that wants the whole tree should use.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import cast

from .models.ast_model import SourceSpan

__all__ = ["to_json", "to_jsonable"]


def to_jsonable(value: object, *, depth: int | None = None) -> object:
    """Convert a model value into JSON-friendly data.

    Scalars, enums, paths, and source spans are emitted in full; dataclasses and
    containers recurse. ``depth`` bounds how many levels are expanded: scalar
    values never count as a level, and at the limit a composite value becomes a
    placeholder string. ``None`` means no limit.

    A :class:`~sattline_parser.ast.WalkEvent` serialises like any other
    dataclass, so ``parents`` becomes a list of ancestor nodes. Serialise
    ``event.node`` instead when only the node is of interest.
    """
    return _convert(value, remaining=depth)


def to_json(value: object, *, depth: int | None = None, compact: bool = False) -> str:
    """Serialise a model value to JSON text.

    ``compact`` emits one line; otherwise the output is indented for reading.
    ``depth`` is passed through to :func:`to_jsonable`.
    """
    payload = to_jsonable(value, depth=depth)
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _convert(value: object, *, remaining: int | None) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if remaining is not None and remaining <= 0:
        return _placeholder(value)
    next_remaining = None if remaining is None else remaining - 1
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, SourceSpan):
        return _span(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, Mapping):
        pairs = cast("Mapping[object, object]", value)
        return {str(key): _convert(item, remaining=next_remaining) for key, item in pairs.items()}
    if isinstance(value, (set, frozenset)):
        members = cast("set[object] | frozenset[object]", value)
        return [_convert(item, remaining=next_remaining) for item in sorted(members, key=_sort_key)]
    if isinstance(value, Sequence):
        items = cast("Sequence[object]", value)
        return [_convert(item, remaining=next_remaining) for item in items]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _convert(getattr(value, field.name), remaining=next_remaining)
            for field in dataclasses.fields(value)
        }
    return repr(value)[:200]


def _sort_key(value: object) -> tuple[str, str]:
    """A stable order for a set, whose iteration order is not meaningful."""
    return (type(value).__name__, repr(value))


def _span(span: SourceSpan) -> dict[str, object]:
    return {"start": span.start, "end": span.end, "line": span.line, "column": span.column}


def _placeholder(value: object) -> str:
    if isinstance(value, Mapping):
        pairs = cast("Mapping[object, object]", value)
        return f"<{len(pairs)} keys>"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = cast("Sequence[object]", value)
        return f"<{len(items)} items>"
    if isinstance(value, (set, frozenset)):
        members = cast("set[object] | frozenset[object]", value)
        return f"<{len(members)} items>"
    return f"<{type(value).__name__}>"
