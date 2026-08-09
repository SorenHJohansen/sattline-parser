# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportUnknownParameterType=false, reportArgumentType=false
"""Edge-case coverage tests driving otherwise-unreached parser-core branches."""

# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportCallIssue=false
import importlib
import pickle
import runpy
import sys
import types
from pathlib import Path

import pytest
from lark import Token, Tree

import sattline_parser
from sattline_parser import api as parser_api
from sattline_parser import fuzz_harness as fuzzharness
from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    BasePicture,
    ModuleHeader,
    ParameterMapping,
    Variable,
    _normalize_variable_ref,
    _variable_ref_name,
)
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
from sattline_parser.utils import formatter

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


def test_render_source_context_guards() -> None:
    assert parser_api._render_source_context("a\nb", line=None, column=1) == ""
    assert parser_api._render_source_context("a\nb", line=5, column=1) == ""
    assert parser_api._render_source_context("a\nb", line=1, column=2) == "a\n ^"


def test_rewrite_summary_location_branches() -> None:
    assert parser_api._rewrite_summary_location("boom", line=None, column=2) == "boom"
    assert parser_api._rewrite_summary_location("boom, at line 1 col 7", line=3, column=4) == "boom, at line 3 col 4"


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

    def _bad_preprocess(_text: str) -> tuple[str, dict[str, str]]:
        raise ValueError("bad decode")

    monkeypatch.setattr(parser_api, "is_compressed", lambda _text: True)
    monkeypatch.setattr(parser_api, "preprocess_sl_text", _bad_preprocess)
    with pytest.raises(ValueError, match="bad decode"):
        parser_api.load_source_text(source_file)


# ---- Formatter edge branches ----


def test_format_expr_skips_illformed_branch_items() -> None:
    if_expr = (
        const.GRAMMAR_VALUE_IF,
        ["not-a-tuple", ("cond", ["then"]), (42,)],
        ["else"],
    )
    assert "IF 'cond'" in formatter.format_expr(if_expr)

    ternary = ("Ternary", ["junk", (True, "X"), (1,)], "Y")
    assert "THEN" in formatter.format_expr(ternary)

    compare = (const.KEY_COMPARE, "A", ["junk", ("==", "B"), (5,), (42, "x"), (">", 1)])
    assert formatter.format_expr(compare) == "'A' == 'B' AND 'A' > 1"


def test_format_expr_empty_tuple() -> None:
    assert formatter.format_expr(()) == "()"


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
    assert groupconn_value({"groupconn": {"x": 1}}) == {"x": 1}
    assert float_tuple((1,), 2) is None
    assert float_tuple(("a", "b"), 2) is None


def test_sfc_mixin_branch_branches() -> None:
    sfc = SFCMixin()
    blocks = sfc.code_blocks([Token("A", "x"), {"enter": [("stmt",)], "active": [1], "exit": [2]}])
    assert len(blocks.enter) == 1


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


def test_variable_ref_helpers() -> None:
    var = Variable(name="vx", datatype="integer")
    assert _variable_ref_name("plain") == "plain"
    assert _variable_ref_name(var) == "vx"
    assert _variable_ref_name({const.KEY_VAR_NAME: 123}) is None
    assert _normalize_variable_ref(var, field_name="target") == {const.KEY_VAR_NAME: "vx"}
    with pytest.raises(TypeError):
        _normalize_variable_ref(123, field_name="target")


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
    assert fuzzharness.is_expected_parse_error(ValueError("x")) is True


# ---- Atheris fuzzer entry modules ----


@pytest.mark.parametrize("module_name", ["comments_fuzzer", "decode_fuzzer", "parser_fuzzer"])
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


def test_parameter_mapping_str_variable_source() -> None:
    mapping = ParameterMapping(
        target={const.KEY_VAR_NAME: "A"},
        source_type=const.TREE_TAG_VARIABLE_NAME,
        is_duration=False,
        is_source_global=False,
        source={const.KEY_VAR_NAME: "B"},
    )
    assert str(mapping) == "A => B"


def test_parameter_mapping_global_source() -> None:
    mapping = ParameterMapping(
        target={const.KEY_VAR_NAME: "A"},
        source_type=const.TREE_TAG_VARIABLE_NAME,
        is_duration=False,
        is_source_global=True,
    )
    assert str(mapping) == "A => GLOBAL"
