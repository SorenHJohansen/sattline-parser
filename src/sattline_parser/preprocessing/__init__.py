"""Source preprocessing for parser-core.

This package transforms or decodes SattLine source *before* parsing:
compressed-format decoding (``compressed``) and comment stripping
(``comments``). It does not know about the Lark grammar or the AST.
"""

from __future__ import annotations

from .comments import CommentStrippedText, strip_sl_comments, strip_sl_comments_with_mapping
from .compressed import SEED_MAPPING, decode_compressed, is_compressed, preprocess_sl_text

__all__ = [
    "SEED_MAPPING",
    "CommentStrippedText",
    "decode_compressed",
    "is_compressed",
    "preprocess_sl_text",
    "strip_sl_comments",
    "strip_sl_comments_with_mapping",
]
