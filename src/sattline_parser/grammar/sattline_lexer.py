"""Contextual lexical analysis with structural (* ... *) comment support.

SattLine comments may nest and may occur at virtually any parser state.
A plain :class:`lark.lexer.ContextualLexer` cannot handle them because the
LALR state machine merges "inside a comment" and "awaiting the next entry"
states, so trailing code would lex as comment text.

This module registers :class:`SattLineLexer` through the ``_plugins`` hook as
the ``ContextualLexer``. It tracks a comment-depth counter *per lexer run*:

* depth ``0``: delegate to the normal per-state contextual lexer.
* depth ``> 0``: delegate to a dedicated comment scanner that only recognizes
  ``COMMENT_START`` / ``COMMENT_END`` / ``COMMENT_TEXT`` and is oblivious to
  the parser state. Nested comments increment the depth; ``COMMENT_END``
  decrements it.

The depth is a generator-local variable inside :meth:`SattLineLexer.lex`. The
lexer instance is shared by the cached parser across parses, so the depth must
never be stored on ``self``: concurrent parses would otherwise corrupt each
other's nested-comment state.

To keep the merged LALR states safe, ``COMMENT_END`` and ``COMMENT_TEXT`` are
removed from every per-state accepted-terminal set (``COMMENT_START`` stays,
since that is how a comment begins in code context).
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from copy import copy
from typing import Any, cast

from lark.exceptions import UnexpectedCharacters, UnexpectedToken
from lark.lexer import BasicLexer, ContextualLexer, LexerState, Token

from sattline_parser.grammar.constants import (
    COMMENT_TERMINALS,
    TOKEN_COMMENT_END,
    TOKEN_COMMENT_START,
    TOKEN_COMMENT_TEXT,
    TOKEN_MODULE_TYPE_NAME,
    TOKEN_NAME,
)

__all__ = ["SattLineLexer"]

#: Terminals that must never be lexed by a per-state (code) lexer.
_COMMENT_BODY_TERMINALS = frozenset({TOKEN_COMMENT_END, TOKEN_COMMENT_TEXT})

#: Whitespace that may separate a definition head from its ``=``.
_WS = " \t\f\r\n"


def _comment_end(text: object, pos: int) -> int:
    """Return the position just past the ``(* ... *)`` comment at ``pos``.

    Comments may nest; the closing run is the first ``*)`` that balances the
    opening runs.
    """
    text = getattr(text, "text", text)
    if not isinstance(text, str):
        raise TypeError("_comment_end requires a str or lark TextSlice")
    depth = 1
    i = pos
    end = len(text)
    while i < end:
        if text.startswith("(*", i):
            depth += 1
            i += 2
        elif text.startswith("*)", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return end


def _module_typedecl_after(text: object, pos: int) -> bool:
    """True when the next code run is ``= MODULEDEFINITION`` (optionally with
    a ``PRIVATE_`` between ``=`` and ``MODULEDEFINITION``), ignoring
    whitespace and comments in between. Used to upgrade a ``NAME`` to
    ``MODULE_TYPE_NAME`` only for genuine module-type definition heads."""
    text = getattr(text, "text", text)
    if not isinstance(text, str):
        raise TypeError("_module_typedecl_after requires a str or lark TextSlice")
    end = len(text)

    def skip() -> None:
        nonlocal pos
        while pos < end:
            if text[pos] in _WS:
                pos += 1
            elif text.startswith("(*", pos):
                pos = _comment_end(text, pos + 2)
            else:
                return

    skip()
    if pos >= end or text[pos] != "=":
        return False
    pos += 1
    skip()
    if text.startswith("PRIVATE_", pos):
        pos += len("PRIVATE_")
        skip()
    if not text.startswith("MODULEDEFINITION", pos):
        return False
    pos += len("MODULEDEFINITION")
    return pos >= end or text[pos] in _WS


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
        #: Accepted-terminal set per LALR state (comment-body terminals removed).
        self._state_accepts = {state: set(accepts) for state, accepts in stripped_states.items()}
        self.root_lexer = self.BasicLexer(self._stripped_conf)

        comment_conf = copy(conf)
        comment_conf.terminals = [conf.terminals_by_name[name] for name in sorted(COMMENT_TERMINALS)]
        # WS must stay inside COMMENT_TEXT so a whole comment body lexes as a
        # single text run instead of being split by the ignore rule.
        comment_conf.ignore = ()
        self._comment_lexer = BasicLexer(comment_conf)

    def lex(self, lexer_state: LexerState, parser_state: Any) -> Iterator[Token]:
        # Per-run depth: this generator runs once per parse, and the lexer
        # instance is shared by the cached parser, so instance state would leak
        # between concurrent parses.
        comment_depth = 0
        try:
            while True:
                if comment_depth > 0:
                    token = self._comment_lexer.next_token(lexer_state, parser_state)
                else:
                    token = self.lexers[parser_state.position].next_token(lexer_state, parser_state)
                token_type = token.type
                if (
                    comment_depth == 0
                    and token_type == TOKEN_NAME
                    and TOKEN_MODULE_TYPE_NAME in self._state_accepts[parser_state.position]
                    and token.end_pos is not None
                    and _module_typedecl_after(cast(str, getattr(lexer_state, "text", "")), token.end_pos)
                ):
                    token_type = token.type = TOKEN_MODULE_TYPE_NAME
                if token_type == TOKEN_COMMENT_START:
                    comment_depth += 1
                elif token_type == TOKEN_COMMENT_END:
                    comment_depth -= 1
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
