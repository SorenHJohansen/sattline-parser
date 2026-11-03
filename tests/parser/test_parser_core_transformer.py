# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_sl_transformer_top_level_helpers_cover_header_quote_and_tree_iteration_edges():
    header_lines = Tree(
        "header_lines",
        [
            Tree("original_file_date_line", [Token("STRING", '"ignored"')]),
            Tree("program_date_line", [Token("STRING", '"2026-04-30, name: UnitProgram"')]),
        ],
    )
    nested_tree = Tree(
        parser_const.TREE_TAG_MODULE_BODY,
        ["beta", Tree(parser_const.TREE_TAG_BASE_MODULE_BODY, ["gamma"])],
    )

    assert _sl_meta_span(SimpleNamespace(line=9, column=3, start_pos=40, end_pos=50)) == SourceSpan(
        start=40, end=50, line=9, column=3
    )
    assert _sl_meta_span(SimpleNamespace(line=9, column=3)) is None
    assert _sl_meta_span(SimpleNamespace(line=None, column=3)) is None
    assert _extract_program_name_from_header_lines(header_lines) == "UnitProgram"
    assert (
        _extract_program_name_from_header_lines(
            Tree("header_lines", [Tree("program_date_line", [Token("STRING", '"no name here"')])])
        )
        is None
    )
    spaced_header_lines = Tree(
        "header_lines",
        [Tree("program_date_line", [Token("STRING", '"2026-04-30, variant: demo, Name: Spaced Program"')])],
    )
    assert _extract_program_name_from_header_lines(spaced_header_lines) == "Spaced Program"
    assert _strip_quoted('"He said ""Hi""\n"') == 'He said "Hi"'
    assert _strip_quoted("plain-text") == "plain-text"
    assert _sl_is_tree(nested_tree) is True
    assert _sl_is_tree("not-a-tree") is False
    assert list(_sl_flatten_items(["alpha", ["delta"], nested_tree])) == ["alpha", "delta", "beta", "gamma"]
    assert list(_iter_tree_children(Tree("wrapper", ["alpha", "beta"]))) == ["alpha", "beta"]
    assert list(_iter_tree_children("not-a-tree")) == []


def test_sl_transformer_start_paths_cover_header_name_and_errors():
    transformer = SLTransformer()

    base_picture = BasePicture(header=_module_header("BasePicture"))
    started = transformer.start(
        [
            Tree("header_lines", [Tree("program_date_line", [Token("STRING", '"2026-04-30, name: Starter"')])]),
            base_picture,
        ]
    )

    assert started is base_picture
    assert started.program_name == "Starter"
    with pytest.raises(ValueError, match="start expected a BasePicture"):
        transformer.start([Tree("header_lines", []), "missing-base-picture"])
