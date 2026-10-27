"""Make the grammar's keyword terminals case-insensitive.

The recovered scanner setup matches keywords case-insensitively
(``00626850``/``0062e3d0``), so ``moduledefinition`` and ``EndDef`` must parse
exactly like ``MODULEDEFINITION`` and ``ENDDEF``. Lark 1.3.1 has no
``case_insensitive`` option, so the resolved grammar is rewritten instead:

* a named terminal defined as a plain string literal *containing letters* becomes
  a scoped case-insensitive regex with a word boundary,
  ``NAME: "Text"`` -> ``NAME: /(?i:Text)\\b/``;
* a named terminal already defined as a regex keeps its body and gains the same
  scope, ``/(?!IF|THEN).../`` -> ``/(?i:(?!IF|THEN)...)/``, which also makes
  ``NAME``'s keyword exclusion list and the ``True``/``False``/``New``/``Old``
  patterns case-insensitive;
* punctuation-only terminals (``"("``, ``":"``, ``";"`` ...) are left as string
  literals, because case folding them is meaningless.

``(?i:...)`` is used rather than a bare ``(?i)`` because Lark concatenates
terminal patterns into one alternation, where a leading flag would be illegal.

Comment text, string literals and quoted identifiers are unaffected: only
terminals defined in the grammar template are rewritten.
"""

from __future__ import annotations

import re

__all__ = ["make_keywords_case_insensitive"]

#: ``TERMINAL.10:   "Literal"`` (optionally with a priority suffix).
_STRING_TERMINAL_RE = re.compile(
    r'^(?P<name>[A-Z][A-Z0-9_]*(?:\.[0-9]+)?):[ \t]*"(?P<literal>[^"\\]+)"[ \t]*$',
    re.MULTILINE,
)
#: ``TERMINAL.10:   /pattern/`` (optionally with a priority suffix).
_REGEX_TERMINAL_RE = re.compile(
    r"^(?P<name>[A-Z][A-Z0-9_]*(?:\.[0-9]+)?):[ \t]*/(?P<body>.+)/[ \t]*$",
    re.MULTILINE,
)


def _as_case_insensitive_terminal(name: str, pattern: str) -> str:
    return f"{name}: /(?i:{pattern})/"


def _string_terminal(match: re.Match[str]) -> str:
    literal = match.group("literal")
    if not any(character.isalpha() for character in literal):
        return match.group(0)
    return _as_case_insensitive_terminal(match.group("name"), re.escape(literal) + r"\b")


def _regex_terminal(match: re.Match[str]) -> str:
    body = match.group("body")
    if body.startswith("(?i:") or not any(character.isalpha() for character in body):
        return match.group(0)
    return _as_case_insensitive_terminal(match.group("name"), body)


def make_keywords_case_insensitive(grammar_text: str) -> str:
    """Return *grammar_text* with keyword terminals matched case-insensitively."""
    text = _STRING_TERMINAL_RE.sub(_string_terminal, grammar_text)
    return _REGEX_TERMINAL_RE.sub(_regex_terminal, text)
