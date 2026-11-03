"""Resolved grammar text and its stable fingerprint.

``sattline.lark`` is a template whose ``{GRAMMAR_VALUE_*}`` /
``{GRAMMAR_REGEX_*}`` placeholders are filled from
:mod:`sattline_parser.grammar.constants`, then rewritten for case-insensitive
keywords. Both the parser build and the cache identity use this one resolved
text, so a grammar change can never leave a stale cache in front of it.

Placeholders are substituted by name rather than through :meth:`str.format`, so
a literal brace in the grammar is written as it reads. Regex quantifiers such
as ``{2,3}`` and any other ``{...}`` text pass through untouched, and a
placeholder whose name has no constant fails loudly instead of reaching Lark.
"""

from __future__ import annotations

import re
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from . import constants as const
from .keywords import make_keywords_case_insensitive

GRAMMAR_PATH = Path(__file__).resolve().parent / "sattline.lark"

if not GRAMMAR_PATH.exists():
    raise RuntimeError(f"Grammar file missing: {GRAMMAR_PATH}")

#: A whole placeholder, e.g. ``{GRAMMAR_VALUE_MODULEDEF}``. Regex quantifiers
#: are digits, so ``{2,3}`` is not a placeholder and is left alone.
_PLACEHOLDER_RE = re.compile(r"\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute_placeholders(text: str, substitutions: dict[str, str]) -> str:
    """Fill every ``{NAME}`` in *text* from *substitutions*.

    An unknown name raises :class:`RuntimeError` with the placeholder spelled
    out, so a typo fails at the template rather than later inside Lark.
    """
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        try:
            return substitutions[name]
        except KeyError:
            missing.add(name)
            return match.group(0)

    resolved = _PLACEHOLDER_RE.sub(replace, text)
    if missing:
        raise RuntimeError(f"Unknown grammar placeholder(s): {', '.join(sorted(missing))}")
    return resolved


@lru_cache(maxsize=1)
def resolved_grammar() -> str:
    """Return the canonical grammar with constants and keyword casing applied."""
    grammar_text = GRAMMAR_PATH.read_text(encoding="utf-8")
    grammar_substitutions = {
        name: getattr(const, name)
        for name in dir(const)
        if name.startswith("GRAMMAR_VALUE_") or name.startswith("GRAMMAR_REGEX_")
    }
    return make_keywords_case_insensitive(_substitute_placeholders(grammar_text, grammar_substitutions))


@lru_cache(maxsize=1)
def grammar_fingerprint() -> str:
    """Return the SHA-256 of :func:`resolved_grammar` as lowercase hex."""
    return sha256(resolved_grammar().encode("utf-8")).hexdigest()


__all__ = ["GRAMMAR_PATH", "grammar_fingerprint", "resolved_grammar"]
