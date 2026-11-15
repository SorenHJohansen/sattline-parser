# pyright: reportPrivateUsage=false
from types import SimpleNamespace

import pytest
from lark import Tree

from sattline_parser.grammar import constants as parser_const
from sattline_parser.models.ast_model import BasePicture, SourceSpan
from sattline_parser.models.header import HeaderInfo
from sattline_parser.transformer._module_shared import flatten_items, meta_span
from sattline_parser.transformer.sl_transformer import (
    SLTransformer,
    _header_description,
    _header_line_text,
    _is_tree,
    _iter_tree_children,
)

from ._parser_core_test_support import _module_header


def test_sl_transformer_top_level_helpers_cover_header_quote_and_tree_iteration_edges():
    nested_tree = Tree(
        parser_const.TREE_TAG_MODULE_BODY,
        ["beta", Tree(parser_const.TREE_TAG_BASE_MODULE_BODY, ["gamma"])],
    )

    assert meta_span(SimpleNamespace(line=9, column=3, start_pos=40, end_pos=50)) == SourceSpan(
        start=40, end=50, line=9, column=3
    )
    assert meta_span(SimpleNamespace(line=9, column=3)) is None
    assert meta_span(SimpleNamespace(line=None, column=3)) is None
    # ``TokensMixin.STRING`` already unquotes, so the header child is a plain str.
    assert _header_line_text(Tree("program_date_line", ["2026-04-30, name: UnitProgram"])) == (
        "2026-04-30, name: UnitProgram"
    )
    assert _header_line_text(Tree("program_date_line", [])) == ""
    assert _is_tree(nested_tree) is True
    assert _is_tree("not-a-tree") is False
    assert list(flatten_items(["alpha", ["delta"], nested_tree])) == ["alpha", "delta", "beta", "gamma"]
    assert list(_iter_tree_children(Tree("wrapper", ["alpha", "beta"]))) == ["alpha", "beta"]
    assert list(_iter_tree_children("not-a-tree")) == []


def test_header_lines_ignores_a_non_tree_and_a_description_without_a_comment():
    transformer = SLTransformer()
    header = transformer.header_lines(
        [
            "ignored",
            Tree("syntax_version_line", ["SyntaxVersion"]),
            Tree("original_file_date_line", ["OriginalFileDate"]),
            Tree("program_date_line", ["ProgramDate"]),
            Tree("change_description", []),
        ]
    )

    assert header.syntax_version_line == "SyntaxVersion"
    assert header.description is None
    assert _header_description(Tree("change_description", [])) is None


def test_header_info_reads_the_editor_fields_and_tolerates_other_spellings():
    header = HeaderInfo(
        syntax_version_line="Syntax version 2.23, date: 2026-04-30-00:00:00.000 N",
        original_file_date_line="Original file date: ---",
        program_date_line="Program date: 2026-04-30-00:00:00.000, Name: Spaced Program",
    )

    assert header.syntax_version == "2.23"
    assert header.original_file_date == "---"
    assert header.program_date == "2026-04-30-00:00:00.000"
    assert header.program_name == "Spaced Program"
    assert header.description is None

    # An unrecognised line keeps its text and yields None for the field it lacks.
    other = HeaderInfo("SyntaxVersion", "OriginalFileDate", "ProgramDate")
    assert (other.syntax_version, other.original_file_date, other.program_date, other.program_name) == (
        None,
        None,
        None,
        None,
    )
    assert HeaderInfo("", "Original file date:", "Program date: 2026-04-30, name:").program_name is None


def test_sl_transformer_start_paths_cover_header_name_and_errors():
    transformer = SLTransformer()

    base_picture = BasePicture(header=_module_header("BasePicture"))
    header = HeaderInfo(
        syntax_version_line="Syntax version 2.23, date: 2026-04-30-00:00:00.000 N",
        original_file_date_line="Original file date: ---",
        program_date_line="Program date: 2026-04-30-00:00:00.000, name: Starter",
    )
    started = transformer.start([header, base_picture])

    assert started is base_picture
    assert started.program_name == "Starter"
    assert started.header_info is header
    with pytest.raises(ValueError, match="start expected a BasePicture"):
        transformer.start([header, "missing-base-picture"])
