"""Source preprocessing for parser-core.

This package decodes compressed SattLine source *before* parsing
(``compressed``). Structural ``(* ... *)`` comments are handled by the
grammar itself (``sattline_parser.grammar.sattline``), not by stripping.

``preprocess_source`` returns a :class:`~sattline_parser.source_document.SourceDocument`
that preserves original-source provenance through decoding.
"""

from __future__ import annotations

from .coded import decode_coded_stream, is_coded
from .compressed import (
    SEED_MAPPING,
    PreprocessError,
    decode_compressed,
    is_compressed,
    preprocess_sl_text,
    preprocess_source,
)

__all__ = [
    "SEED_MAPPING",
    "PreprocessError",
    "decode_coded_stream",
    "decode_compressed",
    "is_coded",
    "is_compressed",
    "preprocess_sl_text",
    "preprocess_source",
]
