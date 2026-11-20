"""Pin the LALR shift/reduce conflicts the grammar resolves silently.

``build_lark_parser`` builds Lark with ``strict=False``, so every shift/reduce
conflict is resolved as a shift and only logged. A grammar edit can therefore
change how an ambiguous input is parsed without any test failing. This module
records the exact conflict set (count, terminal, and the chosen action) so that
a change has to be made deliberately, with the numbers updated here.

The conflicts are all comment or property-separator ambiguity:

- ``COMMENT_START`` (38): a comment may be attached before or after the item it
  precedes, so both a shift (consume the comment as part of the next construct)
  and a reduce (close the current construct first) are possible. Shifting keeps
  the comment attached to the following construct, which is what the grammar
  author intends.
- ``CONNECTIONNODE`` (8): the same shape for a connection property inside
  ``common_properties``. Shifting keeps the connection with the property list.

Resolving these by rewriting the grammar would change the language (comment
attachment and property grouping), so they are pinned rather than removed. The
numbers are for the pinned ``lark`` 1.3.x range; a lark upgrade that changes
conflict analysis fails this test instead of silently changing a parse.
"""

from __future__ import annotations

import logging
from collections import Counter

import pytest
from lark import Lark

from sattline_parser.grammar.resolved import resolved_grammar
from sattline_parser.grammar.sattline_lexer import SattLineLexer

#: Every shift/reduce conflict the grammar currently leaves to Lark's default.
_EXPECTED_CONFLICTS = {"COMMENT_START": 38, "CONNECTIONNODE": 8}


@pytest.fixture(scope="module")
def conflict_messages() -> list[str]:
    """Build the parser once, uncached, and collect Lark's conflict log lines."""
    messages: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    handler = _Collect()
    logger = logging.getLogger("lark")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        Lark(
            resolved_grammar(),
            parser="lalr",
            lexer="contextual",
            regex=True,
            debug=True,
            cache=False,
            _plugins={"ContextualLexer": SattLineLexer},
        )
    finally:
        logger.removeHandler(handler)
    return [message for message in messages if "Shift/Reduce conflict" in message]


def test_the_grammar_has_exactly_the_pinned_shift_reduce_conflicts(conflict_messages: list[str]) -> None:
    assert conflict_messages
    terminals = Counter(message.split("terminal ", 1)[1].split(":", 1)[0] for message in conflict_messages)

    assert len(conflict_messages) == sum(_EXPECTED_CONFLICTS.values())
    assert dict(terminals) == _EXPECTED_CONFLICTS


def test_every_conflict_is_still_resolved_as_a_shift(conflict_messages: list[str]) -> None:
    """The default action is what the pinned numbers assume, so it is pinned too."""
    assert conflict_messages
    assert all("(resolving as shift)" in message for message in conflict_messages)


def test_no_conflict_is_a_reduce_reduce_collision(conflict_messages: list[str]) -> None:
    """A reduce/reduce collision is a hard error, not a silent resolution."""
    assert conflict_messages
    assert not any("Reduce/Reduce" in message for message in conflict_messages)
