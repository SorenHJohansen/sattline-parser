"""Compatibility re-exports from the preprocessing package.

The canonical implementation moved to
``sattline_parser.preprocessing.comments``; this module is kept so that
existing imports and test seams keep working unchanged.
"""

from __future__ import annotations

from ..preprocessing.comments import (
    CommentStrippedText,
    strip_sl_comments,
    strip_sl_comments_with_mapping,
)

__all__ = ["CommentStrippedText", "strip_sl_comments", "strip_sl_comments_with_mapping"]
