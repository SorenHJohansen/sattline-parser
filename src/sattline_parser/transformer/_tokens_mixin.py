"""Token coercion mixin for SLTransformer.

Handles grammar token-to-value conversion: STRING, NAME, numeric and boolean literals,
keywords, and terminal punctuation.
"""

# pyright: reportUnusedClass=false

from __future__ import annotations

from typing import Literal

from lark import Token

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import FloatLiteral, IntLiteral, SourceSpan

DEFAULT_INIT = object()


class TokensMixin:
    """Mixin providing token and terminal coercion methods."""

    def _unwrap_token(self, tok: object) -> str | object:
        """Unwrap a Lark Token to string."""
        if isinstance(tok, Token):
            return str(tok)
        return tok

    # ---- Convert basic terminals to Python values ----

    def NAME(self, tok: Token) -> str:
        """Grammar NAME terminal -> string."""
        return str(tok)

    def STRING(self, tok: Token) -> str:
        """Grammar STRING terminal -> string (strip quotes, unescape)."""
        s = str(tok)
        # STRING includes quotes; "" inside is an escaped quote
        inner = s[1:-1] if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else s
        return inner.replace('""', '"').rstrip("\n")

    def STRING_CRLF(self, tok: Token) -> str:
        """Grammar STRING_CRLF terminal -> string (strip opening quote, drop trailing CR/LF)."""
        s = str(tok)
        # Token is "content\r\n — no closing quote, so strip leading " and trailing newlines
        inner = s[1:] if s.startswith('"') else s
        return inner.replace('""', '"').rstrip("\r\n")

    def _token_span(self, tok: Token) -> SourceSpan | None:
        line = getattr(tok, "line", None)
        column = getattr(tok, "column", None)
        start_pos = getattr(tok, "start_pos", None)
        end_pos = getattr(tok, "end_pos", None)
        if (
            isinstance(line, int)
            and isinstance(column, int)
            and line > 0
            and column > 0
            and isinstance(start_pos, int)
            and isinstance(end_pos, int)
        ):
            return SourceSpan(start=start_pos, end=end_pos, line=line, column=column)
        return None

    def SIGNED_INT(self, tok: Token) -> IntLiteral:
        """Grammar SIGNED_INT terminal -> IntLiteral with source span.

        Clamps to ABB 32-bit signed range [INT_MIN, INT_MAX].
        """
        raw = int(str(tok))
        clamped = max(const.INT_MIN, min(const.INT_MAX, raw))
        return IntLiteral(clamped, self._token_span(tok))

    def SIGNED_INT_NOTAIL(self, tok: Token) -> IntLiteral:
        """Grammar SIGNED_INT_NOTAIL terminal -> IntLiteral (no trailing coordinates)."""
        return self.SIGNED_INT(tok)

    def REAL(self, tok: Token) -> FloatLiteral:
        """Grammar REAL terminal -> FloatLiteral with source span.

        Clamps magnitude to ABB REAL_MAX.
        """
        raw = float(str(tok))
        clamped = max(-const.REAL_MAX, min(const.REAL_MAX, raw)) if raw != 0.0 else raw
        return FloatLiteral(clamped, self._token_span(tok))

    def REAL_NOTAIL(self, tok: Token) -> FloatLiteral:
        """Grammar REAL_NOTAIL terminal -> FloatLiteral (no trailing coordinates)."""
        return self.REAL(tok)

    def BOOL(self, tok: Token) -> bool:
        """Grammar BOOL terminal -> bool."""
        s = str(tok)
        if s == const.GRAMMAR_VALUE_BOOL_TRUE:
            return True
        if s == const.GRAMMAR_VALUE_BOOL_FALSE:
            return False
        raise ValueError(f"BOOL expected {const.GRAMMAR_VALUE_BOOL_TRUE}/{const.GRAMMAR_VALUE_BOOL_FALSE}; got: {s}")

    def BOOL_NOTAIL(self, tok: Token) -> bool:
        """Grammar BOOL_NOTAIL terminal -> bool (no trailing coordinates)."""
        return self.BOOL(tok)

    def STRING_NOTAIL(self, tok: Token) -> str:
        """Grammar STRING_NOTAIL terminal -> string (no trailing coordinates)."""
        return self.STRING(tok)

    # Keywords we care about as flags

    def GLOBAL_KW(self, _tok: object) -> Literal[True]:  # "GLOBAL"
        """Grammar GLOBAL_KW keyword -> True."""
        return True

    def CONST_KW(self, _tok: object) -> str:
        """Grammar CONST_KW keyword -> modifier string."""
        return const.GRAMMAR_VALUE_CONST_KW

    def STATE_KW(self, _tok: object) -> str:
        """Grammar STATE_KW keyword -> modifier string."""
        return const.GRAMMAR_VALUE_STATE_KW

    def OPSAVE_KW(self, _tok: object) -> str:
        """Grammar OPSAVE_KW keyword -> modifier string."""
        return const.GRAMMAR_VALUE_OPSAVE_KW

    def SECURE_KW(self, _tok: object) -> str:
        """Grammar SECURE_KW keyword -> modifier string."""
        return const.GRAMMAR_VALUE_SECURE_KW

    # DEFAULT in init

    def DEFAULT(self, _tok: object) -> object:
        """Grammar DEFAULT terminal -> DEFAULT_INIT sentinel."""
        return DEFAULT_INIT

    # Punctuation tokens we don't need as data (returning None is fine; we'll filter Nones)

    def COLON(self, _tok: object) -> None:
        """Grammar COLON punctuation -> None (filtered out)."""
        return None

    def COMMA(self, _tok: object) -> None:
        """Grammar COMMA punctuation -> None (filtered out)."""
        return None

    def SEMI(self, _tok: object) -> None:
        """Grammar SEMI punctuation -> None (filtered out)."""
        return None

    # And the := and optional Duration_Value inside opt_var_init

    def ASSIGN_INIT_VALUE(self, _tok: object) -> None:
        """Grammar ASSIGN_INIT_VALUE (:=) punctuation -> None (filtered out)."""
        return None

    def DURATION_VALUE(self, _tok: object) -> object:
        """Grammar DURATION_VALUE terminal -> GRAMMAR_VALUE_DURATION_VALUE sentinel."""
        return const.GRAMMAR_VALUE_DURATION_VALUE

    def sl_datecode(self, items: list[object]) -> int:
        """Grammar sl_datecode rule -> int datecode."""
        for it in items:
            if isinstance(it, Token) and it.type == const.KEY_SL_DATECODE:
                try:
                    return int(it.value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid {const.KEY_SL_DATECODE} value: {it.value!r}") from exc
            if isinstance(it, int):
                return it
        raise ValueError(f"sl_datecode expected int or {const.KEY_SL_DATECODE} Token; got: {items}")
