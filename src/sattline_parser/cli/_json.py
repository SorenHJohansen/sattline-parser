"""JSON helpers: a versioned document envelope over the public serializer."""

from __future__ import annotations

import json

from sattline_parser.serialization import to_jsonable

__all__ = ["SCHEMA_PREFIX", "dumps", "to_jsonable"]

#: Every payload the CLI emits is tagged with a versioned schema id.
SCHEMA_PREFIX = "sattline.v1"


def dumps(payload: object, *, compact: bool = False) -> str:
    """Serialise a payload; ``compact`` emits one line."""
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False, indent=2)
