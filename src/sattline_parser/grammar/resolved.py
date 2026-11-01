"""Resolved grammar text and its stable fingerprint.

``sattline.lark`` is a template whose ``{GRAMMAR_VALUE_*}`` /
``{GRAMMAR_REGEX_*}`` placeholders are filled from
:mod:`sattline_parser.grammar.constants`, then rewritten for case-insensitive
keywords. Both the parser build and the cache identity use this one resolved
text, so a grammar change can never leave a stale cache in front of it.
"""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from . import constants as const
from .keywords import make_keywords_case_insensitive

GRAMMAR_PATH = Path(__file__).resolve().parent / "sattline.lark"

if not GRAMMAR_PATH.exists():
    raise RuntimeError(f"Grammar file missing: {GRAMMAR_PATH}")


@lru_cache(maxsize=1)
def resolved_grammar() -> str:
    """Return the canonical grammar with constants and keyword casing applied."""
    grammar_text = GRAMMAR_PATH.read_text(encoding="utf-8")
    grammar_substitutions = {
        name: getattr(const, name)
        for name in dir(const)
        if name.startswith("GRAMMAR_VALUE_") or name.startswith("GRAMMAR_REGEX_")
    }
    return make_keywords_case_insensitive(grammar_text.format(**grammar_substitutions))


@lru_cache(maxsize=1)
def grammar_fingerprint() -> str:
    """Return the SHA-256 of :func:`resolved_grammar` as lowercase hex."""
    return sha256(resolved_grammar().encode("utf-8")).hexdigest()


__all__ = ["GRAMMAR_PATH", "grammar_fingerprint", "resolved_grammar"]
