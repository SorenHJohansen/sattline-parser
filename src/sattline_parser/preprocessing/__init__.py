"""Source preprocessing for parser-core.

This package decodes compressed SattLine source *before* parsing
(``compressed``). Structural ``(* ... *)`` comments are handled by the
grammar itself (``sattline_parser.grammar.sattline``), not by stripping.
"""

from __future__ import annotations

from .compressed import SEED_MAPPING, decode_compressed, is_compressed, preprocess_sl_text

__all__ = [
    "SEED_MAPPING",
    "decode_compressed",
    "is_compressed",
    "preprocess_sl_text",
]
