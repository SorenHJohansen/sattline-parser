"""Contextual lexical analysis with structural (* ... *) comment support.

SattLine comments may nest and may occur at virtually any parser state.
A plain :class:`lark.lexer.ContextualLexer` cannot handle them because the
LALR state machine merges "inside a comment" and "awaiting the next entry"
states, so trailing code would lex as comment text.

This module registers :class:`SattLineLexer` through the ``_plugins`` hook as
the ``ContextualLexer``. It tracks a comment-depth counter:

* depth ``0``: delegate to the normal per-state contextual lexer.
* depth ``> 0``: delegate to a dedicated comment scanner that only recognizes
  ``COMMENT_START`` / ``COMMENT_END`` / ``COMMENT_TEXT`` and is oblivious to
  the parser state. Nested comments increment the depth; ``COMMENT_END``
  decrements it.

To keep the merged LALR states safe, ``COMMENT_END`` and ``COMMENT_TEXT`` are
removed from every per-state accepted-terminal set (``COMMENT_START`` stays,
since that is how a comment begins in code context).
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from copy import copy
from typing import Any

from lark.exceptions import UnexpectedCharacters, UnexpectedToken
from lark.lexer import BasicLexer, ContextualLexer, LexerState, Token

from sattline_parser.grammar.constants import (
    COMMENT_TERMINALS,
    TOKEN_COMMENT_END,
    TOKEN_COMMENT_START,
    TOKEN_COMMENT_TEXT,
)

__all__ = ["SattLineLexer"]

#: Terminals that must never be lexed by a per-state (code) lexer.
_COMMENT_BODY_TERMINALS = frozenset({TOKEN_COMMENT_END, TOKEN_COMMENT_TEXT})


class SattLineLexer(ContextualLexer):
    """ContextualLexer that models structural (* ... *) comments."""

    def __init__(
        self,
        conf: Any,
        states: dict[int, Collection[str]],
        always_accept: Collection[str] = (),
    ) -> None:
        stripped_states = {
            state: [term for term in accepts if term not in _COMMENT_BODY_TERMINALS]
            for state, accepts in states.items()
        }
        self._stripped_conf = copy(conf)
        self._stripped_conf.terminals = [term for term in conf.terminals if term.name not in _COMMENT_BODY_TERMINALS]
        super().__init__(
            conf,
            {state: list(accepts) for state, accepts in stripped_states.items()},
            always_accept=always_accept,
        )
        self.root_lexer = self.BasicLexer(self._stripped_conf)

        self._comment_depth = 0

        comment_conf = copy(conf)
        comment_conf.terminals = [conf.terminals_by_name[name] for name in sorted(COMMENT_TERMINALS)]
        # WS must stay inside COMMENT_TEXT so a whole comment body lexes as a
        # single text run instead of being split by the ignore rule.
        comment_conf.ignore = ()
        self._comment_lexer = BasicLexer(comment_conf)

    def lex(self, lexer_state: LexerState, parser_state: Any) -> Iterator[Token]:
        self._comment_depth = 0
        try:
            while True:
                if self._comment_depth > 0:
                    token = self._comment_lexer.next_token(lexer_state, parser_state)
                else:
                    token = self.lexers[parser_state.position].next_token(lexer_state, parser_state)
                token_type = token.type
                if token_type == TOKEN_COMMENT_START:
                    self._comment_depth += 1
                elif token_type == TOKEN_COMMENT_END:
                    self._comment_depth -= 1
                yield token
        except EOFError:
            pass
        except UnexpectedCharacters as exc:
            # In the contextual lexer, UnexpectedCharacters can mean the
            # terminal is defined but not accepted in the current context.
            # Fall back to the global lexer to produce a nicer error.
            try:
                last_token = lexer_state.last_token
                token = self.root_lexer.next_token(lexer_state, parser_state)
                raise UnexpectedToken(
                    token,
                    exc.allowed,
                    state=parser_state,
                    token_history=[last_token],
                    terminals_by_name=self.root_lexer.terminals_by_name,
                ) from exc
            except UnexpectedCharacters:
                raise exc from None
