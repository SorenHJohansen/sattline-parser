# pyright: reportUnusedClass=false

"""SFC (Sequence Function Chart) mixin for SLTransformer.

Handles sequence elements, transitions, steps, equations, and related SFC constructs.
"""

from __future__ import annotations

from typing import Any, cast

from lark import Token, Tree

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    CodeComment,
    CodeItem,
    Equation,
    ModuleCode,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCCodeBlocks,
    SFCFork,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
)
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    SLExpression,
    TernaryOp,
    UnaryOp,
    VarRef,
)

from ._comments_mixin import is_comment_tree
from ._module_shared import CodeBlockPayload, TransformerItem, TransformerTree, coord_pair, tree_children

SfcBody = list[SFCBodyItem]


class SFCMixin:
    """Mixin providing SFC (sequence function chart) transformation methods."""

    def _flatten_code_body(self, items: list[TransformerItem]) -> list[CodeItem]:
        """Flatten code-comment runs into a flat code list with CodeComment inline."""
        flat: list[CodeItem] = []
        for item in items:
            if isinstance(item, list):
                nested = cast(list[TransformerItem], item)
                for child in nested:
                    if isinstance(child, (Assignment, FuncCallStmt, IfStmt, CodeComment)):
                        flat.append(child)
                    else:
                        raise ValueError(f"code body unexpected item: {type(child).__name__}: {child!r}")
            elif isinstance(item, Token):
                continue
            elif isinstance(item, (Assignment, FuncCallStmt, IfStmt, CodeComment)):
                flat.append(item)
            else:
                raise ValueError(f"code body unexpected item: {type(item).__name__}: {item!r}")
        return flat

    def entercode(self, items: list[TransformerItem]) -> CodeBlockPayload:
        """Grammar entercode -> normalized enter block payload."""
        return CodeBlockPayload(kind="enter", items=tuple(self._flatten_code_body(items)))

    def activecode(self, items: list[TransformerItem]) -> CodeBlockPayload:
        """Grammar activecode -> normalized active block payload."""
        return CodeBlockPayload(kind="active", items=tuple(self._flatten_code_body(items)))

    def exitcode(self, items: list[TransformerItem]) -> CodeBlockPayload:
        """Grammar exitcode -> normalized exit block payload."""
        return CodeBlockPayload(kind="exit", items=tuple(self._flatten_code_body(items)))

    def code_blocks(self, items: list[TransformerItem]) -> SFCCodeBlocks:
        """Grammar code_blocks -> SFCCodeBlocks with enter/active/exit blocks."""
        statements: dict[str, list[CodeItem]] = {"enter": [], "active": [], "exit": []}
        for item in items:
            if not isinstance(item, CodeBlockPayload):
                raise ValueError(f"code_blocks expected CodeBlockPayload items; got: {type(item).__name__}: {item!r}")
            statements[item.kind].extend(item.items)
        return SFCCodeBlocks(
            enter=statements["enter"],
            active=statements["active"],
            exit=statements["exit"],
        )

    def modulecode(self, items: list[TransformerItem]) -> ModuleCode:
        """Grammar modulecode -> ModuleCode with sequences and equations."""
        module_code = ModuleCode()
        sequences: list[Sequence] = []
        equations: list[Equation] = []

        for item in items:
            if isinstance(item, Token):
                continue
            if isinstance(item, Sequence):
                sequences.append(item)
            elif isinstance(item, Equation):
                equations.append(item)
            else:
                raise ValueError(f"modulecode expected Sequence/Equation; got: {type(item).__name__}: {item!r}")

        if sequences:
            module_code.sequences = sequences
        if equations:
            module_code.equations = equations

        return module_code

    def seqinitstep(self, items: list[TransformerItem]) -> SFCStep:
        """Grammar seqinitstep -> SEQINITSTEP NAME? code_blocks seqfork?."""
        return self._step(items, "init", "seqinitstep")

    def _step(self, items: list[TransformerItem], kind: str, rule: str) -> SFCStep:
        """Shared SEQINITSTEP / SEQSTEP shape: name, code blocks, optional fork."""
        name: str | None = None
        code: SFCCodeBlocks | None = None
        fork: SFCFork | None = None
        for item in items:
            if isinstance(item, Token):
                if item.type == "NAME" and name is None:
                    name = str(item)
                continue
            if isinstance(item, SFCFork):
                fork = item
            elif isinstance(item, SFCCodeBlocks):
                code = item
            elif isinstance(item, str) and name is None:
                name = item
            else:
                raise ValueError(f"{rule} unexpected item shape")
        if code is None:
            raise ValueError(f"{rule} expected code_blocks")
        return SFCStep(kind=kind, name=name, code=code, fork=fork)

    def seqstep(self, items: list[TransformerItem]) -> SFCStep:
        """Grammar seqstep -> SEQSTEP NAME? code_blocks seqfork?."""
        return self._step(items, "step", "seqstep")

    def seqtransition(self, items: list[TransformerItem]) -> SFCTransition:
        """Grammar seqtransition -> SEQTRANSITION NAME? (WAIT_FOR expression)? seqfork?.

        Both the name and the guard are optional in the native reader; an absent
        guard is kept as ``None`` because the compiler lowers it to true
        (0070d180, 006fad30) and a round-trip must not invent a ``WAIT_FOR True``.
        """
        items = [item for item in items if not is_comment_tree(item)]
        name: str | None = None
        condition: SLExpression | None = None
        fork: SFCFork | None = None
        wait_seen = False
        for item in items:
            if isinstance(item, Token):
                if item.type == "WAIT_FOR":
                    wait_seen = True
                elif item.type == "NAME" and name is None and not wait_seen:
                    name = str(item)
                continue
            if isinstance(item, SFCFork):
                fork = item
                continue
            if wait_seen and condition is None:
                if not isinstance(
                    item, (VarRef, BoolOp, NotOp, Compare, BinOp, UnaryOp, FuncCall, TernaryOp, bool, int, float, str)
                ):
                    raise ValueError(f"seqtransition expected an expression; got: {type(item).__name__}: {item!r}")
                condition = item
                continue
            if isinstance(item, str) and name is None and not wait_seen:
                name = item
                continue
            raise ValueError(f"seqtransition unexpected item: {type(item).__name__}: {item!r}")
        if wait_seen and condition is None:
            raise ValueError(f"seqtransition expected an expression after WAIT_FOR; got: {items!r}")
        return SFCTransition(name=name, condition=condition, fork=fork)

    def seqtransitionsub(self, items: list[TransformerItem]) -> SFCTransitionSub:
        """Grammar seqtransitionsub -> SUBSEQTRANSITION NAME? sequence_body ENDSUBSEQTRANSITION."""
        if len(items) == 3:
            name: str | None = None
            if not (isinstance(items[1], Tree) and items[1].data == const.KEY_SEQUENCE_BODY):
                raise ValueError(
                    f"seqtransitionsub expected (SUBSEQTRANSITION, sequence_body, ENDSUBSEQTRANSITION); got: {items!r}"
                )  # pragma: no cover
            tree = cast(TransformerTree, items[1])
        elif len(items) == 4 and isinstance(items[1], str):
            name = items[1]
            if not (isinstance(items[2], Tree) and items[2].data == const.KEY_SEQUENCE_BODY):
                raise ValueError(
                    f"seqtransitionsub expected (SUBSEQTRANSITION, NAME, sequence_body, ENDSUBSEQTRANSITION); got: {items!r}"
                )
            tree = cast(TransformerTree, items[2])
        else:
            raise ValueError(
                f"seqtransitionsub expected (SUBSEQTRANSITION, [NAME], sequence_body, ENDSUBSEQTRANSITION); got: {items!r}"
            )  # pragma: no cover
        return SFCTransitionSub(name=name, body=cast(SfcBody, tree_children(tree)))

    def _subsequence_body(self, items: list[TransformerItem], rule: str) -> tuple[str | None, SfcBody]:
        """Shared SUBSEQUENCE / SUBSEQSTEP shape: optional name plus a body."""
        name: str | None = None
        body: SfcBody | None = None
        for item in items:
            if isinstance(item, Token):
                if item.type == "NAME" and name is None:
                    name = str(item)
                continue
            if isinstance(item, str) and name is None:
                name = item
                continue
            if isinstance(item, Tree) and item.data == const.KEY_SEQUENCE_BODY:
                body = cast(SfcBody, tree_children(cast(TransformerTree, item)))
                continue
            raise ValueError(f"{rule} unexpected item in the sub-sequence shape")
        if body is None:
            raise ValueError(f"{rule} expected a sequence_body; got: {items!r}")
        return name, body

    def seqsub(self, items: list[TransformerItem]) -> SFCSubsequence:
        """Grammar seqsub -> SUBSEQUENCE NAME? sequence_body ENDSUBSEQUENCE."""
        name, body = self._subsequence_body(items, "seqsub")
        return SFCSubsequence(name=name, body=body, kind="sequence")

    def seqsubstep(self, items: list[TransformerItem]) -> SFCSubsequence:
        """Grammar seqsubstep -> SUBSEQSTEP NAME? sequence_body ENDSUBSEQSTEP."""
        name, body = self._subsequence_body(items, "seqsubstep")
        return SFCSubsequence(name=name, body=body, kind="substep")

    def _collect_sequence_branches(self, items: list[TransformerItem], rule: str) -> list[SfcBody]:
        branches: list[SfcBody] = []
        for item in items:
            if isinstance(item, Token):
                continue
            if isinstance(item, Tree):
                tree = cast(TransformerTree, item)
                if tree.data != const.KEY_SEQUENCE_BODY:
                    raise ValueError(f"{rule} expected sequence_body Trees; got Tree({tree.data!r})")
                branches.append(cast(SfcBody, tree_children(tree)))
                continue
            raise ValueError(f"{rule} expected sequence_body Trees; got: {type(item).__name__}: {item!r}")
        if not branches:
            raise ValueError(f"{rule} expected at least two sequence_body branches; got: {items!r}")
        return branches

    def seqalternative(self, items: list[TransformerItem]) -> SFCAlternative:
        """Grammar seqalternative -> ALTERNATIVESEQ sequence_body (ALTERNATIVEBRANCH sequence_body)+ ENDALTERNATIVE."""
        branches = self._collect_sequence_branches(items, "seqalternative")
        return SFCAlternative(branches=branches)

    def seqparallel(self, items: list[TransformerItem]) -> SFCParallel:
        """Grammar seqparallel -> PARALLELSEQ sequence_body (PARALLELBRANCH sequence_body)+ ENDPARALLEL."""
        branches = self._collect_sequence_branches(items, "seqparallel")
        return SFCParallel(branches=branches)

    def seqfork(self, items: list[TransformerItem]) -> SFCFork:
        """Grammar seqfork -> SEQFORK NAME ("," NAME)* SEQBREAK?."""
        targets: list[str] = []
        has_break = False
        for item in items:
            if isinstance(item, Token):
                if item.type == "SEQBREAK":
                    has_break = True
                elif item.type == "NAME":
                    targets.append(str(item))
                continue
            if type(item) is str:
                targets.append(item)
        targets_tuple = tuple(targets)
        if not targets_tuple:
            raise ValueError(f"seqfork expected at least one NAME target; got: {items!r}")
        return SFCFork(targets=targets_tuple, has_break=has_break)

    def seq_element(self, items: list[TransformerItem]) -> TransformerItem:
        """Grammar seq_element -> passthrough SFC node."""
        for item in items:
            return item
        raise ValueError("seq_element expected an SFC element; got no items")

    def sequence_body(self, items: list[TransformerItem]) -> TransformerTree:
        """Grammar sequence_body -> Tree of SFC sequence elements with CodeComments inline."""
        flat: list[Any] = []
        for item in items:
            if isinstance(item, list):
                flat.extend(cast(list[Any], item))
            else:
                flat.append(item)
        return Tree(const.KEY_SEQUENCE_BODY, flat)

    def sequence(self, items: list[TransformerItem]) -> Sequence:
        """Grammar sequence -> Sequence with name, position, size, seqcontrol/seqtimer flags, code."""
        name: str | None = None
        position: tuple[float, float] | None = None
        size: tuple[float, float] | None = None
        seqcontrol = False
        seqtimer = False
        code: list[SFCBodyItem] = []
        seqtype = const.GRAMMAR_VALUE_SEQUENCE

        for item in items:
            if isinstance(item, Token):
                if item.type == const.GRAMMAR_VALUE_SEQUENCE:
                    seqtype = const.GRAMMAR_VALUE_SEQUENCE
                elif item.type == const.GRAMMAR_VALUE_OPENSEQUENCE:
                    seqtype = const.GRAMMAR_VALUE_OPENSEQUENCE
                continue

            if isinstance(item, str) and name is None:
                name = item
                continue

            coord = coord_pair(item)
            if coord is not None:
                if position is None:
                    position = coord
                elif size is None:
                    size = coord
                continue

            if isinstance(item, Tree) and item.data == const.KEY_SEQ_CONTROL_OPS:
                tree = cast(TransformerTree, item)
                for child in tree_children(tree):
                    if not isinstance(child, Token):
                        continue
                    # Keyword case is folded by the scanner, so compare folded.
                    spelling = str(child.value).casefold()
                    if spelling == const.GRAMMAR_VALUE_SEQCONTROL.casefold():
                        seqcontrol = True
                    elif spelling == const.GRAMMAR_VALUE_SEQTIMER.casefold():
                        seqtimer = True
                continue

            if isinstance(item, Tree) and item.data == const.KEY_SEQUENCE_BODY:
                tree = cast(TransformerTree, item)
                for child in tree_children(tree):
                    if isinstance(child, Token):
                        continue
                    if isinstance(
                        child,
                        (
                            SFCStep,
                            SFCTransition,
                            SFCTransitionSub,
                            SFCAlternative,
                            SFCParallel,
                            SFCSubsequence,
                            CodeComment,
                        ),
                    ):
                        code.append(child)
                    else:
                        raise ValueError(f"sequence unexpected code item: {type(child).__name__}: {child!r}")

        if position is None:
            raise ValueError("Position can't be None")
        if size is None:
            raise ValueError("Size can't be None")

        return Sequence(
            name=name,
            type=seqtype,
            position=position,
            size=size,
            seqcontrol=seqcontrol,
            seqtimer=seqtimer,
            code=code,
        )

    def equationblock(self, items: list[TransformerItem]) -> Equation:
        """Grammar equationblock -> Equation; name/position/size are optional.

        Native 00726030 accepts ``EQUATIONBLOCK``/``EQUATIONS`` with no name and
        no coordinate/size metadata, so absence is preserved as ``None``.
        """
        name: str | None = None
        position: tuple[float, float] | None = None
        size: tuple[float, float] | None = None
        code: list[CodeItem] = []
        layer_info: int | None = None

        for item in items:
            if isinstance(item, Token):
                continue

            if isinstance(item, int):
                if layer_info is None:
                    layer_info = item
                continue

            if isinstance(item, str) and name is None:
                name = item
                continue

            coord = coord_pair(item)
            if coord is not None:
                if position is None:
                    position = coord
                elif size is None:
                    size = coord
                continue

            if isinstance(item, (Assignment, FuncCallStmt, IfStmt, CodeComment)):
                code.append(item)
            else:
                raise ValueError(f"equationblock unexpected code item: {type(item).__name__}: {item!r}")

        return Equation(name=name, position=position, size=size, code=code, layer_info=layer_info)


__all__ = ["SFCMixin"]
