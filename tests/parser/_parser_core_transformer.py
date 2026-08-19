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


def test_sl_transformer_helper_methods_cover_nested_tail_and_payload_collection():
    transformer = SLTransformer()
    variable_tail = VarRef("ScanGroup")
    tuple_tail = ("Group", 3)

    tails = transformer._extract_coord_tails(
        [
            None,
            Token("NAME", "IgnoredToken"),
            IntLiteral(1),
            FloatLiteral(2.5),
            True,
            "TailText",
            (1.0, 2.0),
            tuple_tail,
            variable_tail,
            {"nested": ["NestedTail", {"deep": "DeepTail"}]},
            [Tree("inner", ["TreeTail"])],
        ]
    )

    assert tails == ["TailText", tuple_tail, variable_tail, "NestedTail", "DeepTail", "TreeTail"]
    assert transformer._merge_tails(["Left"], [], ["Right"]) == ["Left", "Right"]
    assert transformer._extract_coord_payloads(
        [
            InterimCoords(coords=(1.0, 2.0), tails=["CoordTail"]),
            (3.0, 4.0),
            "ignored",
        ]
    ) == ([(1.0, 2.0), (3.0, 4.0)], ["CoordTail"])


def test_sl_transformer_tailed_rule_and_start_paths_cover_enable_payloads_and_errors():
    transformer = SLTransformer()
    enable_expr = Tree(parser_const.KEY_ENABLE_EXPRESSION, ["Enabled"])
    dict_payload = {"payload": "Width"}

    assert transformer._extract_tailed_rule_payload("plain") is None
    assert (
        transformer._extract_tailed_rule_payload(Tree("format_string_tailed", [Token("COMMA", ","), enable_expr]))
        is enable_expr
    )
    assert (
        transformer._extract_tailed_rule_payload(Tree("width_tailed", [Token("COMMA", ","), dict_payload]))
        == dict_payload
    )
    assert transformer._extract_tailed_rule_payload(Tree("width_tailed", [Token("COMMA", ",")])) is None

    invar_tree = Tree(parser_const.GRAMMAR_VALUE_INVAR_PREFIX, [])
    tail_tree = Tree("invar_tail", [])
    tailed_rule = Tree("format_string_tailed", [Token("COMMA", ","), {"payload": "FormatTail"}])
    collected = transformer._collect_invar_enable_tails(
        [
            {parser_const.KEY_TAIL: "PlainTail", "nested": [invar_tree]},
            {parser_const.TREE_TAG_ENABLE: True, parser_const.KEY_TAIL: "EnabledTail"},
            Tree("outer", cast(list[Any], [enable_expr, tail_tree, tailed_rule])),
            [None],
        ]
    )

    assert "PlainTail" in collected
    assert "EnabledTail" in collected
    assert invar_tree in collected
    assert enable_expr in collected
    assert tail_tree in collected
    assert {"payload": "FormatTail"} in collected

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
