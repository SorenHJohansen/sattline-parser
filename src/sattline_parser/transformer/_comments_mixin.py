"""Role-tagged comment handling for the SattLine transformer.

The grammar exposes comments through role-specific nodes (``code_comment``,
``module_description_comment``, ``module_end_comment``). This mixin converts
each role node into a :class:`CodeComment` and provides helpers so consumers
can keep code comments inline in code lists or discard generic comment trees
in non-code contexts.
"""

from __future__ import annotations

from typing import cast

from lark import Token, Tree

from sattline_parser.models.ast_model import CodeComment, SourceSpan

from ._module_shared import TransformerItem, TransformerTree, tree_children

#: Tree data names of the generic (discard) comment rules. Role rules transform
#: to CodeComment; these stay as Trees outside code/description/end contexts.
COMMENT_TREE_NAMES = frozenset({"comment", "comments"})


def is_comment_tree(value: object) -> bool:
    """Return True when *value* is a generic comment tree that must be skipped.

    Used to keep comments from corrupting position-sensitive transformer rules
    (e.g. ``seqtransition``) in contexts where they are discarded from the AST.
    """
    return isinstance(value, Tree) and cast(TransformerTree, value).data in COMMENT_TREE_NAMES


class CommentsMixin:
    """Mixin providing role-tagged comment transformation methods."""

    def _comment_pieces(self, comment_tree: TransformerTree) -> list[Token]:
        """Return the token stream of a structural ``comment`` tree, in order.

        Nested comment trees are unwrapped so the concatenation of token values
        reconstructs the exact comment source text including delimiters.
        """
        pieces: list[Token] = []
        for child in tree_children(comment_tree):
            if isinstance(child, Token):
                pieces.append(child)
            elif isinstance(child, Tree):
                pieces.extend(self._comment_pieces(cast(TransformerTree, child)))
        return pieces

    def _build_code_comment(self, items: list[TransformerItem]) -> CodeComment:
        """Build a CodeComment from a single structural ``comment`` tree."""
        if not items:
            raise ValueError("comment rule expected a structural comment tree; got no items")
        comment_tree = cast(TransformerTree, items[0])
        pieces = self._comment_pieces(comment_tree)
        text = "".join(str(tok) for tok in pieces)
        span: SourceSpan | None = None
        if pieces:
            first_span = cast(SourceSpan | None, self._token_span(pieces[0]))  # type: ignore[attr-defined]
            last_span = cast(SourceSpan | None, self._token_span(pieces[-1]))  # type: ignore[attr-defined]
            if first_span is not None and last_span is not None:
                span = SourceSpan(
                    start=first_span.start,
                    end=last_span.end,
                    line=first_span.line,
                    column=first_span.column,
                )
        return CodeComment(text=text, span=span)

    def code_comment(self, items: list[TransformerItem]) -> CodeComment:
        """Grammar code_comment -> CodeComment kept inline in ModuleCode lists."""
        return self._build_code_comment(items)

    def module_typedescription(self, items: list[TransformerItem]) -> CodeComment:
        """Grammar module_typedescription -> CodeComment (module type description)."""
        return self._build_code_comment(items)

    def module_end_comment(self, items: list[TransformerItem]) -> CodeComment:
        """Grammar module_end_comment -> CodeComment (trailing ENDDEF marker)."""
        return self._build_code_comment(items)

    def comment_stmt(self, items: list[TransformerItem]) -> CodeComment:
        """Grammar comment_stmt -> CodeComment (comment used as a null statement)."""
        return self._build_code_comment(items)


__all__ = ["CommentsMixin", "is_comment_tree"]
