"""Compatibility re-exports from the preprocessing package.

The canonical implementation moved to
``sattline_parser.preprocessing.compressed``; this module is kept so that
existing imports and test seams keep working unchanged.
"""

from __future__ import annotations

from ..preprocessing.compressed import (
    SEED_MAPPING,
    decode_compressed,
    is_compressed,
    preprocess_sl_text,
)

__all__ = ["SEED_MAPPING", "decode_compressed", "is_compressed", "preprocess_sl_text"]
