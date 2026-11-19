"""Text-level fidelity harness for the whole-file formatter.

An AST equality check is blind to a value the model never stored: if the
transformer drops a clause, the source tree and the reparsed output are equal
because neither holds it, and ``unittest`` sees a clean round trip. This module
therefore compares the *written construct text* instead.

The comparison is a canonical token stream. Both texts are parsed with a parser
that keeps every terminal, including anonymous punctuation and comments, and the
leaves are flattened in source order into ``(token type, value)`` pairs. The
stream is then canonicalised by the normalisations the model documents. A
construct the formatter drops, duplicates, or changes therefore shows up as a
missing or extra token, named by the failure message together with the fixture.

Pinned normalisations, all of them documented in ``docs/ast.md``:

* keyword, modifier, and builtin-datatype case is folded through the language
  identifier table, because the model stores the canonical spelling;
* a numeric token compares by value, because the formatter re-spells
  ``1.00`` as ``1.0``;
* a declaration group is expanded to one declaration per name, because the
  model holds one ``Variable`` per name and the formatter regroups adjacent
  declarations that share a type;
* statement separators and grouping parentheses are dropped, because neither is
  modelled: grouping is carried by the tree, and the grammar fixes where a
  separator belongs (the reparse below proves the output is valid);
* an empty code-block keyword is dropped, because the model stores an empty
  block as an empty list and the formatter writes only non-empty blocks;
* a boolean keyword compares as ``TRUE``/``FALSE``, because ``On``/``Off`` and
  ``True``/``False`` are one value in the model.

Two shapes are pinned per fixture, because the model genuinely reorders or
normalises them:

* ``ModuleCode`` keeps sequences and equations in two lists, so their written
  interleaving is not modelled (the formatter writes sequences first);
* a text object's clauses are written in the formatter's fixed clause order,
  and its free label text is not modelled at all.

The second test in this module checks the other direction: every model field
that carries written source is either read by the formatter or listed as a
deliberate omission, so a newly added field fails until it is handled.
"""

from __future__ import annotations

import ast as pyast
import dataclasses
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
from lark import Lark, Token, Tree

from sattline_parser import ast as ast_surface
from sattline_parser.api import parse_source_file, parse_source_text
from sattline_parser.ast import Assignment, IntLiteral, UnaryOp
from sattline_parser.formatting import format_source
from sattline_parser.grammar import constants as const
from sattline_parser.grammar.resolved import resolved_grammar
from sattline_parser.grammar.sattline_lexer import SattLineLexer
from sattline_parser.models.properties import GraphProperties, InteractProperties
from sattline_parser.names import fold_identifier
from sattline_parser.preprocessing import preprocess_source

_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
_FORMATTING = Path(__file__).resolve().parents[2] / "src" / "sattline_parser" / "formatting"

#: One canonical token: its terminal name and its normalised value.
type _Token = tuple[str, str]

#: Tokens whose spelling or position is not modelled, dropped from both sides.
_IGNORED_TOKENS = frozenset(
    {
        "SEMICOLON",  # a statement separator, fixed by the grammar
        "LPAR",  # grouping, carried by the tree
        "RPAR",
        "ENTERCODE",  # an empty code block is an empty list in the model
        "ACTIVECODE",
        "EXITCODE",
    }
)

#: Boolean spellings the model folds into one ``bool`` value.
_TRUE_WORDS = frozenset({"true", "on"})
_FALSE_WORDS = frozenset({"false", "off"})

#: Declaration punctuation, used to canonicalise a written group.
_NAME = "NAME"
_COMMA = "COMMA"
_COLON = "COLON"
_SEMICOLON = "SEMICOLON"
_DESCRIPTION_TOKENS = frozenset({"STRING", "STRING_NOTAIL"})


@dataclass(frozen=True)
class _PinnedNormalisation:
    """One fixture whose token text the formatter normalises by design.

    ``summary`` names the normalisation in the failure message. ``source_only``
    and ``formatted_only`` list tokens the formatter is allowed to remove or add,
    one occurrence per entry, and each entry must still be present: a stale pin
    is a failure, because it no longer describes the fixture.
    """

    summary: str
    compare_order: bool = True
    source_only: tuple[_Token, ...] = ()
    formatted_only: tuple[_Token, ...] = ()


_MODULE_CODE_SECTIONS = (
    "ModuleCode stores sequences and equations in two sections, so the formatter "
    "writes every sequence before every equation instead of the written interleaving"
)
_TEXT_OBJECT_CLAUSES = (
    "a text object's clauses are written in the formatter's clause order, and its free label text is not modelled"
)

#: The fixtures whose written text the model genuinely reorders or normalises.
_PINNED: dict[str, _PinnedNormalisation] = {
    "CommentInsideEquation.s": _PinnedNormalisation(summary=_MODULE_CODE_SECTIONS, compare_order=False),
    "GraphicsObjects.s": _PinnedNormalisation(summary=_TEXT_OBJECT_CLAUSES, compare_order=False),
    "GraphObjectGeometry.s": _PinnedNormalisation(summary=_TEXT_OBJECT_CLAUSES, compare_order=False),
    "GraphObjectEnableTails.s": _PinnedNormalisation(
        summary=_TEXT_OBJECT_CLAUSES,
        compare_order=False,
        source_only=(("STRING_NOTAIL", '"DisplayValue"'),),
    ),
    "GraphObjectsObjectLayer.s": _PinnedNormalisation(
        summary=_TEXT_OBJECT_CLAUSES,
        source_only=(("STRING_NOTAIL", '"DisplayValue"'),),
        formatted_only=(("STRING_NOTAIL", '""'),),
    ),
    "CompressedFullGrammar.s": _PinnedNormalisation(
        summary=_TEXT_OBJECT_CLAUSES,
        compare_order=False,
        source_only=(
            ("STRING_NOTAIL", '"NodeVar"'),
            ("STRING_NOTAIL", '"NodeVar"'),
            ("STRING_NOTAIL", '"NodeVar2"'),
            ("STRING_NOTAIL", '"TextLeft"'),
            ("STRING_NOTAIL", '"TextCenter"'),
            ("STRING_NOTAIL", '"TextRight"'),
        ),
        formatted_only=(("STRING_NOTAIL", '""'),),
    ),
    "UnCompressedFullGrammar.s": _PinnedNormalisation(
        summary=_TEXT_OBJECT_CLAUSES,
        compare_order=False,
        source_only=(
            ("STRING_NOTAIL", '"NodeVar"'),
            ("STRING_NOTAIL", '"NodeVar"'),
            ("STRING_NOTAIL", '"NodeVar2"'),
            ("STRING_NOTAIL", '"TextLeft"'),
            ("STRING_NOTAIL", '"TextCenter"'),
            ("STRING_NOTAIL", '"TextRight"'),
        ),
        formatted_only=(("STRING_NOTAIL", '""'),),
    ),
}


def _fixtures() -> list[Path]:
    return sorted([*_CORPUS.glob("valid/*.s"), *_CORPUS.glob("edge_cases/*.s")])


@cache
def _token_parser() -> Lark:
    """A parser that keeps every terminal, including anonymous punctuation."""
    return Lark(
        resolved_grammar(),
        start="start",
        parser="lalr",
        lexer="contextual",
        regex=True,
        keep_all_tokens=True,
        _plugins={"ContextualLexer": SattLineLexer},
    )


def _leaf_tokens(text: str) -> list[Token]:
    """Every terminal in *text*, in source order."""
    tree: Tree[Token] = _token_parser().parse(text)  # pyright: ignore[reportUnknownMemberType]
    leaves: list[Token] = []
    stack: list[Tree[Token] | Token] = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, Tree):
            stack.extend(reversed(node.children))
        else:
            leaves.append(node)
    return leaves


def _raw_tokens(text: str) -> list[_Token]:
    return [(token.type, str(token)) for token in _leaf_tokens(text)]


def _expand_declaration_groups(tokens: list[_Token]) -> list[_Token]:
    """Write every declaration group as one declaration per name.

    The model holds one ``Variable`` per name, so ``A, B: integer`` and two
    separate ``A: integer``/``B: integer`` declarations are the same tree. The
    formatter regroups adjacent declarations that share a type, which changes the
    written punctuation and repeats the datatype. Expanding both sides removes
    that difference without hiding a declaration: a dropped name or initializer
    is still a missing token.
    """
    expanded: list[_Token] = []
    index = 0
    total = len(tokens)
    while index < total:
        token = tokens[index]
        if token[0] != _NAME:
            expanded.append(token)
            index += 1
            continue
        names: list[tuple[str, str | None]] = [(token[1], None)]
        cursor = index + 1
        if cursor < total and tokens[cursor][0] in _DESCRIPTION_TOKENS:
            names[0] = (token[1], tokens[cursor][1])
            cursor += 1
        while cursor + 1 < total and tokens[cursor][0] == _COMMA and tokens[cursor + 1][0] == _NAME:
            name = tokens[cursor + 1][1]
            cursor += 2
            description: str | None = None
            if cursor < total and tokens[cursor][0] in _DESCRIPTION_TOKENS:
                description = tokens[cursor][1]
                cursor += 1
            names.append((name, description))
        if cursor >= total or tokens[cursor][0] != _COLON:
            expanded.append(token)
            index += 1
            continue
        end = cursor + 1
        while end < total and tokens[end][0] != _SEMICOLON:
            end += 1
        if end >= total:
            expanded.append(token)
            index += 1
            continue
        tail = tokens[cursor + 1 : end]
        for name, description in names:
            expanded.append((_NAME, name))
            if description is not None:
                expanded.append(("STRING", description))
            expanded.extend(((_COLON, ":"), *tail, (_SEMICOLON, ";")))
        index = end + 1
    return expanded


def _canonical(tokens: list[_Token]) -> list[_Token]:
    """Fold the spelling normalisations the model documents."""
    canonical: list[_Token] = []
    for kind, value in tokens:
        if kind in _IGNORED_TOKENS:
            continue
        if kind in {"SIGNED_INT", "SIGNED_INT_NOTAIL"}:
            canonical.append(("NUMBER", str(int(value))))
            continue
        if kind in {"REAL", "REAL_NOTAIL"}:
            canonical.append(("NUMBER", repr(float(value))))
            continue
        folded = value.casefold()
        if folded in _TRUE_WORDS:
            canonical.append(("BOOL", "TRUE"))
            continue
        if folded in _FALSE_WORDS:
            canonical.append(("BOOL", "FALSE"))
            continue
        if value[:1].isalpha() or value[:1] == "_":
            # A keyword, modifier, or builtin datatype is stored in its
            # canonical spelling. An identifier keeps its own spelling in the
            # model, and the AST round-trip tests pin that separately.
            canonical.append((_NAME if kind == _NAME else "WORD", fold_identifier(value)))
            continue
        canonical.append((kind, value))
    return canonical


def _stream(text: str) -> list[_Token]:
    return _canonical(_expand_declaration_groups(_raw_tokens(text)))


def _stream_for(path: Path) -> tuple[list[_Token], list[_Token]]:
    """The canonical source and formatted streams for one fixture."""
    document = preprocess_source(path.read_text(encoding="cp1252"))
    picture = parse_source_file(path, log_failures=False)
    formatted = format_source(picture)
    # The output has to be valid source in its own right. A construct the
    # formatter wrote somewhere the grammar rejects fails here, not silently.
    parse_source_text(formatted, log_failures=False)
    return _stream(document.normalized_text), _stream(formatted)


def _remove_pinned(stream: list[_Token], pinned: tuple[_Token, ...], side: str, name: str) -> list[_Token]:
    remaining = list(stream)
    for token in pinned:
        if token not in remaining:
            pytest.fail(
                f"{name}: the pinned normalisation is stale: {side} no longer contains "
                f"{token!r}, so the fixture changed. Re-derive the pin instead of widening it."
            )
        remaining.remove(token)
    return remaining


def _describe(counter: Counter[_Token]) -> str:
    if not counter:
        return "nothing"
    items = ", ".join(f"{kind} {value!r} x{count}" for (kind, value), count in sorted(counter.items()))
    return items


def _fail_stream(path: Path, expected: list[_Token], actual: list[_Token], ordered: bool) -> None:
    missing = Counter(expected) - Counter(actual)
    extra = Counter(actual) - Counter(expected)
    detail: str
    if missing or extra:
        detail = f"missing from the formatted text: {_describe(missing)}; added: {_describe(extra)}"
    else:
        index = next(
            position for position, (left, right) in enumerate(zip(expected, actual, strict=False)) if left != right
        )
        window = slice(max(index - 2, 0), index + 3)
        detail = (
            "the same tokens appear in a different order: "
            f"at token {index}, source wrote {expected[window]!r}, formatted wrote {actual[window]!r}"
        )
    label = "" if ordered else " (compared as an inventory because the fixture is pinned as reordered)"
    pytest.fail(f"{path.name}: the formatted text does not preserve the constructs the source wrote{label}: {detail}")


@pytest.mark.parametrize("path", _fixtures(), ids=lambda path: path.name)
def test_formatted_text_preserves_every_written_construct(path: Path) -> None:
    expected, actual = _stream_for(path)
    pinned = _PINNED.get(path.name)
    if pinned is None:
        if expected != actual:
            _fail_stream(path, expected, actual, ordered=True)
        return
    expected = _remove_pinned(expected, pinned.source_only, "the source", path.name)
    actual = _remove_pinned(actual, pinned.formatted_only, "the formatted text", path.name)
    if pinned.compare_order:
        if expected != actual:
            _fail_stream(path, expected, actual, ordered=True)
        return
    if Counter(expected) != Counter(actual):
        _fail_stream(path, expected, actual, ordered=False)


# ---------------------------------------------------------------------------
# Formatter field coverage
# ---------------------------------------------------------------------------

#: Model types that do not describe written source, with the reason.
_NOT_SOURCE = {
    "SourceSpan": "layout metadata for a position, never written back as a value",
    "WalkEvent": "traversal payload, not a model value",
    "LiteralLeaf": "traversal payload, not a model value",
    "GraphicsBinding": "project graphics value, not an AST node and never formatted",
    "InteractorPropertySpec": "interactor catalogue vocabulary, not written source",
    "TypedInteractorProperty": "a clause paired with its catalogue spec, not written source",
}

#: Fields the formatter deliberately does not write, keyed by ``Class.field``.
#: Each reason is repeated in the omission table in ``docs/ast.md``.
_OMITTED: dict[str, str] = {
    "BasePicture.origin_file": "project provenance of the loaded file, not part of its text",
    "BasePicture.origin_lib": "project provenance of the loading root, not part of its text",
    "BasePicture.program_name": "derived from the written program date line, which is written",
    "DataType.origin_file": "project provenance of the loaded file, not part of its text",
    "DataType.origin_lib": "project provenance of the loading root, not part of its text",
    "ModuleTypeDef.origin_file": "project provenance of the loaded file, not part of its text",
    "ModuleTypeDef.origin_lib": "project provenance of the loading root, not part of its text",
    "ParameterMapping.source_type": "derived: the formatter writes the source or the literal that is set",
    "LitStringTail.keyword": "one grammar spelling, written from the grammar constant",
}

#: Deepest shipped docs file that carries the omission table.
_DOCS = Path(__file__).resolve().parents[2] / "docs" / "ast.md"


def _model_classes() -> list[type[object]]:
    """Every AST dataclass on the supported surface, in name order."""
    classes: list[type[object]] = []
    for name in sorted(ast_surface.__all__):
        value = getattr(ast_surface, name)
        if isinstance(value, type) and dataclasses.is_dataclass(value) and name not in _NOT_SOURCE:
            classes.append(value)
    return classes


def _source_fields() -> dict[str, str]:
    """The field inventory, derived from the model rather than the formatter.

    The key is ``Class.field`` and the value is the bare field name. A layout
    field (a span or a geometry value) is skipped: it records where a construct
    was, not what it said. Every other field carries written source until the
    omission table says otherwise.
    """
    fields: dict[str, str] = {}
    for cls in _model_classes():
        for field in dataclasses.fields(cast("Any", cls)):
            if field.metadata.get("layout"):
                continue
            fields[f"{cls.__name__}.{field.name}"] = field.name
    return fields


def _formatter_names() -> set[str]:
    """Attribute names and property keys the formatter reads anywhere.

    The scan is deliberately name-based: a field name the formatter reads on any
    class counts as emitted. A field only one class owns therefore still fails
    until that class's field is read, and the omission table stays the place a
    deliberate gap is recorded.
    """
    names: set[str] = set()
    for path in sorted(_FORMATTING.glob("*.py")):
        module = pyast.parse(path.read_text(encoding="utf-8"))
        for node in pyast.walk(module):
            if isinstance(node, pyast.Attribute):
                names.add(node.attr)
                if isinstance(node.value, pyast.Name) and node.value.id == "const":
                    value = getattr(const, node.attr, None)
                    if isinstance(value, str):
                        names.add(value)
    return names


def test_every_source_field_is_written_or_exempted() -> None:
    emitted = _formatter_names()
    gaps = [key for key, name in _source_fields().items() if name not in emitted and key not in _OMITTED]
    assert not gaps, (
        "the formatter neither writes these model fields nor lists them as a deliberate "
        "omission; write the field or add a reasoned entry to the omission table in "
        f"docs/ast.md: {gaps}"
    )


def test_the_omission_table_names_only_real_fields_and_is_documented() -> None:
    fields = _source_fields()
    docs = _DOCS.read_text(encoding="utf-8")
    stale = [key for key in _OMITTED if key not in fields]
    undocumented = [key for key in _OMITTED if key not in docs]
    assert not stale, f"the omission table names fields the model no longer has: {stale}"
    assert not undocumented, f"these deliberate omissions are not documented in docs/ast.md: {undocumented}"


def test_every_typed_property_key_is_written() -> None:
    """A property key is model state too, so it needs an emitted key or a reason."""
    emitted = _formatter_names()
    gaps: list[str] = []
    for name, properties in (("GraphProperties", GraphProperties), ("InteractProperties", InteractProperties)):
        for key in properties.__annotations__:
            if key not in emitted and f"{name}.{key}" not in _OMITTED:
                gaps.append(f"{name}.{key}")
    assert not gaps, (
        "these typed property keys are neither written by the formatter nor listed as a "
        f"deliberate omission in docs/ast.md: {gaps}"
    )


def test_every_pinned_fixture_exists() -> None:
    names = {path.name for path in _fixtures()}
    stale = sorted(set(_PINNED) - names)
    assert not stale, f"the pinned-normalisation table names fixtures that no longer exist: {stale}"


_PROBE = (
    '"Syntax version 2.23"\n'
    '"Original file date: ---"\n'
    '"Program date: ---, name: Probe"\n'
    "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "Grid = 0.2\n"
    "ENDDEF (*BasePicture*);\n"
)


def test_the_harness_sees_a_dropped_clause() -> None:
    """The comparison must fail on a lost clause, or it proves nothing."""
    picture = parse_source_text(_PROBE, log_failures=False)
    formed = format_source(picture)
    assert "Grid = 0.2" in formed

    dropped = formed.replace("Grid = 0.2\n", "")

    missing = Counter(_stream(_PROBE)) - Counter(_stream(dropped))
    assert missing, "a dropped Grid clause did not change the canonical token stream"
    assert ("WORD", "GRID") in missing
    assert ("NUMBER", "0.2") in missing


def test_a_unary_sign_over_a_literal_survives_the_format_pass() -> None:
    """`- 5` is a `UnaryOp`; `-5` is a literal. The written form decides."""
    source = _PROBE.replace(
        "Grid = 0.2\n",
        "ModuleCode\n   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n      A = - 5;\n      B = -5;\n",
    )
    picture = parse_source_text(source, log_failures=False)
    assert picture.modulecode is not None
    assert picture.modulecode.equationblocks is not None
    code = picture.modulecode.equationblocks[0].code
    assert isinstance(code[0], Assignment)
    assert isinstance(code[0].value, UnaryOp)
    assert isinstance(code[1], Assignment)
    assert type(code[1].value) is IntLiteral

    formed = format_source(picture)

    assert "A = - 5" in formed
    assert "B = -5" in formed
    reparsed = parse_source_text(formed, log_failures=False)
    assert reparsed == picture


def test_module_code_sections_are_written_sequences_first() -> None:
    """The model keeps two sections, so the written interleaving is normalised."""
    source = (
        '"Syntax version 2.23"\n'
        '"Original file date: ---"\n'
        '"Program date: ---, name: Sections"\n'
        "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   Cmd: boolean := False;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   SEQUENCE First (SEQCONTROL) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        "      SEQINITSTEP Init\n"
        "      ENTERCODE\n"
        "         Cmd = True;\n"
        "      SEQTRANSITION Start WAIT_FOR Cmd\n"
        "   ENDSEQUENCE\n"
        "   EQUATIONBLOCK Calc COORD 0.0, 0.5 OBJSIZE 1.0, 1.0 :\n"
        "      Cmd = False;\n"
        "   SEQUENCE Second (SEQCONTROL) COORD 0.0, 1.0 OBJSIZE 1.0, 1.0\n"
        "      SEQINITSTEP Init\n"
        "      SEQTRANSITION Again WAIT_FOR Cmd\n"
        "   ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source, log_failures=False)
    assert picture.modulecode is not None
    assert picture.modulecode.sequences is not None
    assert len(picture.modulecode.sequences) == 2

    formed = format_source(picture)

    assert formed.index("SEQUENCE First") < formed.index("SEQUENCE Second") < formed.index("EQUATIONBLOCK Calc")
    assert parse_source_text(formed, log_failures=False) == picture
