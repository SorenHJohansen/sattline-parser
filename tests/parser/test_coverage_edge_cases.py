# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportUnknownParameterType=false, reportArgumentType=false
"""Edge-case coverage tests driving otherwise-unreached parser-core branches."""

# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportCallIssue=false
import importlib
import pickle
import runpy
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lark import Token, Tree
from lark.exceptions import UnexpectedInput

import sattline_parser
from sattline_parser import api as parser_api
from sattline_parser import fuzz_harness as fuzzharness
from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    BasePicture,
    CodeComment,
    ModuleHeader,
    ParameterMapping,
    SourceSpan,
)
from sattline_parser.models.expressions import IfStmt, VarRef
from sattline_parser.source_document import SourceDocument
from sattline_parser.transformer._comments_mixin import CommentsMixin
from sattline_parser.transformer._expressions_mixin import _ExpressionsMixin
from sattline_parser.transformer._graphics_interact_mixin import _as_float, _is_coord_box, _is_coord_pair
from sattline_parser.transformer._module_assembly_mixin import ModuleAssemblyMixin
from sattline_parser.transformer._module_header_mixin import (
    _collect_module_header_argument_tails,
    _normalize_module_header_tail,
)
from sattline_parser.transformer._module_layout_mixin import ModuleLayoutMixin
from sattline_parser.transformer._module_shared import float_tuple, groupconn_value  # used below
from sattline_parser.transformer._sfc_mixin import SFCMixin
from sattline_parser.transformer._tokens_mixin import TokensMixin

from ._parser_core_test_support import _GraphicsHarness

# ---- Package __getattr__ / __dir__ ----


def test_package_lazy_fuzz_exports_and_dir() -> None:
    for name in sattline_parser._FUZZ_EXPORT_SET:
        sattline_parser.__dict__.pop(name, None)
    assert sattline_parser.FuzzResult is not None
    for name in sattline_parser._FUZZ_EXPORT_SET:
        sattline_parser.__dict__.pop(name, None)
    assert sattline_parser.fuzz_harness is not None
    assert isinstance(dir(sattline_parser), list)
    with pytest.raises(AttributeError):
        _ = sattline_parser.does_not_exist_anywhere


# ---- api.py helpers ----


def test_failure_details_without_source() -> None:
    details = parser_api._failure_details(ValueError("demonstrative"))
    assert details.message == "demonstrative"
    assert details.line is None
    assert details.column is None


def test_log_parser_failure_line_without_column(caplog: pytest.LogCaptureFixture) -> None:
    error = ValueError("ow")
    error.line = 1  # type: ignore[attr-defined]
    parser_api._log_parser_failure(stage="parse", exc=error)
    assert any("(line 1)" in record.message for record in caplog.records)


def test_read_text_with_fallback_raises_oserror() -> None:
    missing = Path(__file__).parent / "_this_file_must_not_exist.s"
    with pytest.raises(OSError):
        parser_api.read_text_with_fallback(missing)


def test_load_source_text_decode_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source_file = tmp_path / "compressed.s"
    source_file.write_text("#01#01#01", encoding="utf-8")

    def _bad_preprocess(_text: str) -> SourceDocument:
        raise ValueError("bad decode")

    monkeypatch.setattr(parser_api, "is_compressed", lambda _text: True)
    monkeypatch.setattr(parser_api, "preprocess_source", _bad_preprocess)
    with pytest.raises(ValueError, match="bad decode"):
        parser_api.load_source_text(source_file)


# ---- Formatter edge branches ----


# ---- Transformer mixin helpers ----


def test_coord_type_guards_and_as_float() -> None:
    assert _is_coord_pair("nope") is False
    assert _is_coord_box("nope") is False
    with pytest.raises(ValueError):
        _as_float(object())


def test_module_header_tail_normalization() -> None:
    assert isinstance(_normalize_module_header_tail(Tree("other", ["x"])), Tree)
    assert isinstance(_normalize_module_header_tail(Tree(const.GRAMMAR_VALUE_INVAR_PREFIX, [1, 2])), Tree)
    assert isinstance(_normalize_module_header_tail(Tree(const.GRAMMAR_VALUE_INVAR_PREFIX, [Token("A", "a")])), Tree)
    assert _normalize_module_header_tail(Tree(const.GRAMMAR_VALUE_INVAR_PREFIX, ["child"])) == "child"


def test_module_header_tail_collection_branches() -> None:
    assert _collect_module_header_argument_tails({const.TREE_TAG_ENABLE: True}) == []
    assert _collect_module_header_argument_tails({const.KEY_TAIL: "t"}) == ["t"]
    assert _collect_module_header_argument_tails({"nested": {"leaf": 1}}) == []
    assert _collect_module_header_argument_tails(Tree(const.GRAMMAR_VALUE_INVAR_PREFIX, ["top"])) == ["top"]
    assert _collect_module_header_argument_tails(Tree("unrelated", ["a", Token("N", "n"), None])) == []
    assert _collect_module_header_argument_tails(["e1", {"k": "v"}]) == []
    assert _collect_module_header_argument_tails((1, {"xx": 2})) == []


def test_module_direct_mixin_branches() -> None:
    m = ModuleAssemblyMixin()
    with pytest.raises(ValueError, match="missing ModuleHeader"):
        m.base_picture_module([object()])
    with pytest.raises(ValueError, match="missing variable name"):
        m.variable_item(None, [])
    assert m.variable_item(None, ["name", "desc"]) == ("name", "desc", None)
    variables = m.variable_group([("x", None, None), "INT", (1, 2, 3)])
    assert variables[0].init_value == (1, 2, 3)


def test_module_layout_grid_and_def_tails() -> None:
    layout = ModuleLayoutMixin()
    assert layout.grid([2]) == 2.0
    with pytest.raises(ValueError, match="grid expected"):
        layout.grid([{"bad": 1}])
    module_def = layout.moduledef(
        [
            {const.GRAMMAR_VALUE_CLIPPINGBOUNDS: ((0.0, 0.0), (1.0, 1.0)), const.KEY_TAILS: ["a"]},
            {const.GRAMMAR_VALUE_CLIPPINGBOUNDS: ((2.0, 2.0), (3.0, 3.0)), const.KEY_TAILS: ["b"]},
        ]
    )
    assert module_def.properties[const.KEY_TAILS] == ["a", "b"]


def test_module_shared_float_tuple_and_groupconn() -> None:
    assert groupconn_value(None) is None
    assert groupconn_value({"groupconn": VarRef("ScanGroup")}) == VarRef("ScanGroup")
    assert groupconn_value({"groupconn": {"x": 1}}) is None
    assert float_tuple((1,), 2) is None
    assert float_tuple(("a", "b"), 2) is None


def test_sfc_mixin_branch_branches() -> None:
    sfc = SFCMixin()
    blocks = sfc.code_blocks([{"enter": [("stmt",)], "active": [1], "exit": [2]}])
    assert len(blocks.enter) == 1
    with pytest.raises(ValueError, match="code_blocks expected block payload"):
        sfc.code_blocks([Token("A", "x")])


def test_comment_build_raises_on_empty_items() -> None:
    with pytest.raises(ValueError, match="comment rule expected"):
        CommentsMixin()._build_code_comment([])


def test_expressions_if_statement_flattens_nested_list_statements() -> None:
    mixin = _ExpressionsMixin()
    meta = SimpleNamespace(line=1, column=1, start_pos=1, end_pos=2)
    span = SourceSpan(start=1, end=2, line=1, column=1)
    if_items = [
        Token(const.GRAMMAR_VALUE_IF, "IF"),
        "cond",
        Token("THEN", "THEN"),
        ["stmt1", "stmt2"],
        Token(const.GRAMMAR_VALUE_ENDIF, "ENDIF"),
    ]
    assert mixin.if_statement(meta, if_items) == IfStmt(
        branches=(("cond", ("stmt1", "stmt2")),),
        else_block=None,
        span=span,
    )
    if_else_items = [
        Token(const.GRAMMAR_VALUE_IF, "IF"),
        "cond",
        Token("THEN", "THEN"),
        "stmt",
        Token(const.GRAMMAR_VALUE_ELSE, "ELSE"),
        ["else1", "else2"],
        Token(const.GRAMMAR_VALUE_ENDIF, "ENDIF"),
    ]
    assert mixin.if_statement(meta, if_else_items) == IfStmt(
        branches=(("cond", ("stmt",)),),
        else_block=("else1", "else2"),
        span=span,
    )


def test_text_object_skips_comment_trees_when_linking_text_vars() -> None:
    mixin = _GraphicsHarness(coord_tails=[], extra_tails=[])
    go = mixin.text_object(
        [
            "Caption",
            Tree("comment", [Token("COMMENT", "(* c *)")]),
            Token(const.TOKEN_VARNAME, "TextVar"),
        ]
    )
    assert go.properties["text_vars"] == ["Caption"]


def test_sfc_flatten_code_body_extends_nested_lists() -> None:
    sfc = SFCMixin()
    assert sfc._flatten_code_body([["stmt1", "stmt2"], Token("ENTERCODE", "ENTERCODE")]) == ["stmt1", "stmt2"]


def test_sfc_modulecode_appends_top_level_code_comments() -> None:
    sfc = SFCMixin()
    comment = CodeComment("(* c *)")
    module_code = sfc.modulecode([comment])
    assert module_code.comments == [comment]


def test_sfc_sequence_body_extends_nested_lists() -> None:
    sfc = SFCMixin()
    body = sfc.sequence_body([["step1", "step2"], "step3"])
    assert body.data == const.KEY_SEQUENCE_BODY
    assert body.children == ["step1", "step2", "step3"]


def test_sfc_equationblock_appends_code_comments() -> None:
    sfc = SFCMixin()
    comment = CodeComment("(* c *)")
    equation = sfc.equationblock(["EqA", (1, 2), (3, 4), comment])
    assert equation.code == [comment]


def test_sequence_with_seq_control_tokens() -> None:
    seq = SFCMixin().sequence(
        [
            "myseq",
            (5.0, 6.0),
            (7.0, 8.0),
            Tree(const.KEY_SEQ_CONTROL_OPS, [Token(const.GRAMMAR_VALUE_SEQTIMER, "SEQTIMER"), 44]),
            Tree(const.KEY_SEQUENCE_BODY, ["stmt"]),
        ]
    )
    assert seq.name == "myseq"


def test_token_span_none_when_no_position() -> None:
    literal = TokensMixin().SIGNED_INT(Token("SIGNED_INT", "-7"))
    assert literal is not None


# ---- ast_model helpers ----


def test_base_picture_pickle_roundtrip() -> None:
    basepic = BasePicture(header=ModuleHeader(name="", invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0)))
    basepic.parse_tree = Tree("start2", [])
    restored = pickle.loads(pickle.dumps(basepic))
    assert restored.parse_tree is None


def test_base_picture_setstate_backfills_fields() -> None:
    restored = BasePicture.__new__(BasePicture)
    restored.__setstate__({"_custom": 1})
    assert restored.name == "BasePicture"
    assert restored.parse_tree is None


# ---- fuzz harness ----


def test_repo_root_raises_at_filesystem_root() -> None:
    with pytest.raises(RuntimeError):
        fuzzharness._repo_root_from(Path("/nonexistent/repo/root/nowhere"))


def test_optional_repo_root_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fuzzharness, "_repo_root_from", lambda _anchor: (_ for _ in ()).throw(RuntimeError("no")))
    assert fuzzharness._optional_repo_root_from(Path(".")) is None


def test_collect_corpus_without_corpus_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fuzzharness, "CORPUS_DIR", None)
    assert fuzzharness.collect_corpus_inputs() == []


def test_is_expected_parse_error_public_wrapper() -> None:
    from lark.exceptions import UnexpectedToken  # noqa: PLC0415

    assert fuzzharness.is_expected_parse_error(UnexpectedToken("TOK", "value")) is True
    # Broad built-ins are NOT expected: an internal transformer ValueError is a crash.
    assert fuzzharness.is_expected_parse_error(ValueError("x")) is False
    assert fuzzharness.is_expected_parse_error(SyntaxError("x")) is False


# ---- Atheris fuzzer entry modules ----


@pytest.mark.parametrize("module_name", ["decode_fuzzer", "parser_fuzzer"])
def test_fuzzer_entry_modules(monkeypatch: pytest.MonkeyPatch, module_name: str) -> None:
    calls: list[str] = []
    fake_atheris = types.SimpleNamespace(
        Setup=lambda _argv, _fn: calls.append("setup"),
        Fuzz=lambda: calls.append("fuzz"),
    )
    monkeypatch.setitem(sys.modules, "atheris", fake_atheris)

    module = importlib.import_module(f"sattline_parser.{module_name}")
    module.test_one_input(b"data")
    runpy.run_path(Path(module.__file__).resolve(), run_name="__main__")
    assert "setup" in calls and "fuzz" in calls


def test_decode_fuzzer_absorbs_only_expected_preprocess_errors() -> None:
    from sattline_parser import decode_fuzzer  # noqa: PLC0415

    # Unknown marker -> PreprocessError -> absorbed, no crash.
    decode_fuzzer.test_one_input(b"#XX")
    # Plain text -> no error.
    decode_fuzzer.test_one_input(b"just text")


def test_parser_fuzzer_propagates_internal_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    from sattline_parser import parser_fuzzer  # noqa: PLC0415

    class InternalTransformerError(ValueError):
        pass

    def _explode(_source: str, **kwargs: object) -> object:
        raise InternalTransformerError("internal transformer failure")

    monkeypatch.setattr(parser_fuzzer, "parse_source_text", _explode)
    with pytest.raises(InternalTransformerError, match="internal transformer failure"):
        parser_fuzzer.test_one_input(b"anything")


def test_parameter_mapping_str_variable_source() -> None:
    mapping = ParameterMapping(
        target=VarRef("A"),
        source_type=const.TREE_TAG_VARIABLE_NAME,
        is_duration=False,
        is_source_global=False,
        source=VarRef("B"),
    )
    assert str(mapping) == "A => B"


def test_parameter_mapping_global_source() -> None:
    mapping = ParameterMapping(
        target=VarRef("A"),
        source_type=const.TREE_TAG_VARIABLE_NAME,
        is_duration=False,
        is_source_global=True,
    )
    assert str(mapping) == "A => GLOBAL"


# ---- Source provenance branch coverage ----


def test_source_document_map_position_negative_returns_none() -> None:
    doc = SourceDocument.identity("abc")
    assert doc.map_position(-1) is None
    assert doc.map_position(-5) is None


def test_source_document_map_position_fully_generated_anchors_to_zero() -> None:
    doc = SourceDocument("X", "GGG", (-1, -1, -1))
    assert doc.map_position(0) == 0
    assert doc.map_position(2) == 0


def test_source_document_map_range_fully_generated_uses_whole_original() -> None:
    doc = SourceDocument("hello", "GGGGG", (-1, -1, -1, -1, -1))
    assert doc.map_range(0, 5) == (0, 5)
    doc2 = SourceDocument("hello world", "GGGGG", (-1, -1, -1, -1, -1))
    assert doc2.map_range(0, 5) == (0, 11)


def test_source_document_map_range_generated_suffix_walks_forward() -> None:
    # "ab" original, normalized "abGG" where "GG" is generated.
    doc = SourceDocument("ab", "abGG", (0, 1, -1, -1))
    assert doc.map_range(2, 4) == (1, 2)
    # Fully generated range extends to the end of the original text.
    doc2 = SourceDocument("abc", "GGG", (-1, -1, -1))
    assert doc2.map_range(0, 3) == (0, 3)
    # Forward walk passes over a generated char before finding a mapped anchor.
    doc3 = SourceDocument("A", "XGG", (0, -1, -1))
    assert doc3.map_range(1, 2) == (0, 1)


def test_source_document_map_position_clamps_out_of_range_offsets() -> None:
    doc = SourceDocument("ab", "ab", (0, 1))
    assert doc.map_position(100) == 1
    doc2 = SourceDocument("X", "GG", (-1, -1))
    assert doc2.map_position(1) == 0
    empty = SourceDocument("", "", ())
    assert empty.map_position(0) == 0


def test_remap_parse_error_updates_unexpected_characters_context() -> None:
    from lark.exceptions import UnexpectedCharacters  # noqa: PLC0415

    from sattline_parser.source_document import remap_parse_error  # noqa: PLC0415

    # normalized "abXY", original "aXYb" (Y and b swapped).
    doc = SourceDocument("aXYb", "abXY", (0, 3, 1, 2))
    exc = UnexpectedCharacters("abXY", 2, 1, 3, allowed=cast(Any, {"NAME"}))
    remap_parse_error(exc, doc)
    assert exc.pos_in_stream == 1
    assert exc.char == "X"
    assert exc._context is not None


def test_remap_parse_error_ignores_non_unexpected_input() -> None:
    from sattline_parser.source_document import remap_parse_error  # noqa: PLC0415

    exc = ValueError("plain failure")
    remap_parse_error(exc, SourceDocument.identity("abc"))
    assert str(exc) == "plain failure"
    assert not hasattr(exc, "_sattline_remapped")


def test_remap_tree_handles_negative_token_positions() -> None:
    from sattline_parser.source_document import remap_tree_to_original  # noqa: PLC0415

    # A token with a negative start_pos cannot be mapped; the walk must not crash.
    doc = SourceDocument("abcdef", "Xbcdef!", (0, 0, 2, 3, 4, 5, -1))
    tree = cast(Any, Tree("wrapper", [Token("NAME", "x", start_pos=-5, end_pos=-4)]))
    remap_tree_to_original(tree, doc)
    assert tree.children[0].start_pos == -5


def test_remap_tree_skips_tokens_without_positions() -> None:
    from sattline_parser.source_document import remap_tree_to_original  # noqa: PLC0415

    doc = SourceDocument("abcdef", "Xbcdef!", (0, 0, 2, 3, 4, 5, -1))
    tree = cast(Any, Tree("wrapper", [Token("NAME", "x")]))
    remap_tree_to_original(tree, doc)
    assert tree.children[0].line is None


def test_remap_tree_handles_negative_meta_positions() -> None:
    from sattline_parser.source_document import remap_tree_to_original  # noqa: PLC0415

    doc = SourceDocument("abcdef", "Xbcdef!", (0, 0, 2, 3, 4, 5, -1))
    tree = cast(Any, Tree("wrapper", [Token("NAME", "x", start_pos=0, end_pos=1)]))
    tree.meta.start_pos = -3
    tree.meta.end_pos = -2
    tree.meta.line = 1
    tree.meta.column = 1
    remap_tree_to_original(tree, doc)
    assert tree.meta.start_pos == -3


def test_load_source_text_returns_plain_text_unchanged(tmp_path: Path) -> None:
    plain_file = tmp_path / "plain.s"
    plain_file.write_text("not compressed at all", encoding="utf-8")
    assert parser_api.load_source_text(plain_file) == "not compressed at all"


def test_parse_source_text_emits_debug_for_compressed_input() -> None:
    events: list[str] = []

    from ._parser_core_provenance import _COMPRESSED  # noqa: PLC0415

    parser_api.parse_source_text(_COMPRESSED, debug=events.append)
    assert "Compressed format detected; decoding before parsing" in events


def test_parse_source_file_emits_debug(tmp_path: Path) -> None:
    events: list[str] = []
    file_path = tmp_path / "Program.s"
    file_path.write_text(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*);\n",
        encoding="utf-8",
    )
    parser_api.parse_source_file(file_path, debug=events.append)
    assert f"Parsing file: {file_path}" in events


def test_log_parser_failure_without_source_text(caplog: pytest.LogCaptureFixture) -> None:
    parser_api._log_parser_failure(stage="boom", exc=ValueError("no source"))
    assert any("Parser boom failure" in r.message for r in caplog.records)


def test_parse_source_text_log_failures_disabled_paths() -> None:
    # Parse-error path with logging disabled.
    with pytest.raises(UnexpectedInput):
        parser_api.parse_source_text("garbage input", log_failures=False)
    # Decode-error path with logging disabled.
    with pytest.raises(ValueError):
        parser_api.parse_source_text("#ZZ", log_failures=False)

    # Transform-error path with logging disabled.
    class _BrokenTransformer:
        def transform(self, _tree: object) -> object:
            raise RuntimeError("transform boom")

    with pytest.raises(RuntimeError, match="transform boom"):
        parser_api.parse_source_text(
            '"SyntaxVersion"\n"OriginalFileDate"\n"ProgramDate"\n'
            "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
            "ModuleDef\n"
            "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "ENDDEF (*BasePicture*);\n",
            transformer=_BrokenTransformer(),
            log_failures=False,
        )


def test_opaque_registry_string_text_lookup_failures() -> None:
    from sattline_parser.preprocessing.compressed import _OpaqueRegistry  # noqa: PLC0415

    registry = _OpaqueRegistry('"a string"')
    assert registry.string_text("not-a-placeholder") is None
    assert registry.string_text("\x00C0\x00") is None  # comment slot, not a string
    assert registry.string_text("\x00S9\x00") is None  # out-of-range index
    assert registry.string_text("\x00S") is None  # malformed placeholder
    assert registry.string_text("\x00Sxx\x00") is None  # non-numeric index


def test_opaque_registry_restore_rejects_unknown_placeholder() -> None:
    from sattline_parser.preprocessing.compressed import PreprocessError, _OpaqueRegistry  # noqa: PLC0415

    registry = _OpaqueRegistry('"a string"')
    with pytest.raises(PreprocessError, match="unknown placeholder"):
        registry.restore("\x00S9\x00", [-1, -1, -1, -1, -1, -1])


def test_opaque_registry_restore_detects_unrestored_nul() -> None:
    from sattline_parser.preprocessing.compressed import PreprocessError, _OpaqueRegistry  # noqa: PLC0415

    registry = _OpaqueRegistry('"a string"')
    with pytest.raises(PreprocessError, match="placeholder not restored"):
        registry.restore("\x00leftover", [0, -1, -1, -1, -1, -1, -1, -1])
