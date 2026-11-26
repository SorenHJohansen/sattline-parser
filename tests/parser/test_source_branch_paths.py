# pyright: reportPrivateUsage=false
"""Branch paths in source provenance, decoding, and AST traversal helpers.

Every test here exercises a branch that the ordinary corpus does not reach. The
assertions pin the observable contract of the branch, not just that the line ran.
"""

from __future__ import annotations

import logging
from typing import cast

import pytest
from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedCharacters

from sattline_parser import SourceTooDeepError, parse_source_text
from sattline_parser import source_io as parser_api
from sattline_parser.models import ast_model as m
from sattline_parser.models.clauses import Alignment, FlagClause
from sattline_parser.models.expressions import VarRef
from sattline_parser.models.interactor_properties import typed_interactor_properties
from sattline_parser.models.walk import iter_child_nodes, iter_literal_leaves
from sattline_parser.preprocessing import MAX_IDE_LINE_LENGTH, render_ide_text
from sattline_parser.preprocessing.compressed import PreprocessError
from sattline_parser.source_document import SourceDocument, is_remapped, remap_parse_error

_PLAIN_PROGRAM = (
    '"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-04-23-12:00:00.000, name: BranchPaths"\n'
    "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ENDDEF (*BasePicture*);\n"
)

_PARSER_LOG = "sattline_parser"


def _parser_log_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == _PARSER_LOG]


def test_typed_interactor_properties_skips_a_body_entry_that_is_not_a_property() -> None:
    alignment = Alignment("left")
    visible = FlagClause("Visible_")
    interact = m.InteractObject("TextBox_", properties={"body": [alignment, visible]})

    typed = typed_interactor_properties(interact)

    assert [item.name for item in typed] == ["Visible_"]


def test_iter_child_nodes_skips_a_non_node_item_in_a_sequence_argument() -> None:
    reference = VarRef("A")

    assert list(iter_child_nodes([reference, 3])) == [("[0]", reference)]


def test_iter_literal_leaves_skips_a_non_node_item_in_a_sequence_argument() -> None:
    leaves = list(iter_literal_leaves([VarRef("A"), 3]))

    assert [(leaf.field, leaf.value) for leaf in leaves] == [("name", "A")]


def test_render_ide_text_scans_a_comment_region_as_opaque() -> None:
    raw = "x" * (MAX_IDE_LINE_LENGTH + 20) + " (* comment *)"

    assert len(raw) > MAX_IDE_LINE_LENGTH
    assert render_ide_text(raw) == raw


def test_remap_parse_error_leaves_an_error_without_an_integer_position_alone() -> None:
    document = SourceDocument.identity("abc\n")
    error = UnexpectedCharacters("abc\n", 1, 1, 2)
    error.pos_in_stream = None  # pyright: ignore[reportAttributeAccessIssue]

    remap_parse_error(error, document)

    assert not is_remapped(error)
    assert error.line == 1
    assert error.column == 2


def test_remap_parse_error_leaves_an_error_with_an_unmappable_position_alone() -> None:
    document = SourceDocument.identity("abc\n")
    error = UnexpectedCharacters("abc\n", 1, 1, 2)
    error.pos_in_stream = -1

    remap_parse_error(error, document)

    assert not is_remapped(error)
    assert error.line == 1
    assert error.column == 2


def test_decode_compressed_source_raises_silently_when_logging_is_disabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=_PARSER_LOG)
    caplog.clear()

    with pytest.raises(PreprocessError, match="Unknown compressed marker"):
        parser_api._decode_compressed_source("#01#00", log_failures=False)

    assert _parser_log_records(caplog) == []


def test_parse_source_text_logs_nothing_for_a_decode_failure_when_disabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=_PARSER_LOG)
    caplog.clear()

    with pytest.raises(PreprocessError, match="Unknown compressed marker"):
        parse_source_text("#01#00", log_failures=False)

    assert _parser_log_records(caplog) == []


def test_recursion_error_in_the_parser_is_silent_when_logging_is_disabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _RecursiveParser:
        def parse(self, _text: str) -> Tree[Token]:
            raise RecursionError("boom")

    caplog.set_level(logging.DEBUG, logger=_PARSER_LOG)
    caplog.clear()

    with pytest.raises(SourceTooDeepError):
        parse_source_text(_PLAIN_PROGRAM, parser=cast(Lark, _RecursiveParser()), log_failures=False)

    assert _parser_log_records(caplog) == []
