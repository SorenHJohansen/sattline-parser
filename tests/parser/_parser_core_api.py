# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
import logging

from ._parser_core_test_support import *


def test_parser_api_import_raises_when_grammar_file_is_missing(monkeypatch: pytest.MonkeyPatch):
    module_path = Path(parser_api.__file__)
    module_name = "sattline_parser.api_missing_grammar_test"
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path == parser_api.GRAMMAR_PATH:
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    temp_module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)

    try:
        with pytest.raises(RuntimeError, match="Grammar file missing"):
            spec.loader.exec_module(temp_module)
    finally:
        sys.modules.pop(module_name, None)


def test_parse_source_file_accepts_valid_file(tmp_path):
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
    A: integer := 0;
    B: integer := 1;
    C: integer := 2;
    D: integer := 3;
    X: integer := 0;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        X = IF A > 0 THEN B ELSE C + D ENDIF;
ENDDEF (*BasePicture*);
"""
    source_file = tmp_path / "ValidProgram.s"
    source_file.write_text(code, encoding="utf-8")

    bp = parse_source_file(source_file)

    assert bp.name == "BasePicture"


def test_parser_core_reuses_default_parser(monkeypatch):
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
    A: integer := 0;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        A = A + 1;
ENDDEF (*BasePicture*);
"""

    call_count = 0
    real_create_parser = parser_api.create_parser
    parser_api._default_parser.cache_clear()

    def counting_create_parser():
        nonlocal call_count
        call_count += 1
        return real_create_parser()

    monkeypatch.setattr(parser_api, "create_parser", counting_create_parser)

    parser_api.parse_source_text(code)
    parser_api.parse_source_text(code)

    assert call_count == 1
    parser_api._default_parser.cache_clear()


def test_create_parser_uses_regex_and_disk_cache(monkeypatch, tmp_path):
    captured: dict[str, object] = {}
    cache_dir = tmp_path / "lark-cache"

    class DummyLark:
        def __init__(self, grammar, **options):
            captured["grammar"] = grammar
            captured["options"] = options

    monkeypatch.setattr(parser_api, "Lark", DummyLark)
    monkeypatch.setattr(parser_api, "_PARSER_CACHE_DIR", cache_dir)
    parser = parser_api.create_parser()

    assert isinstance(parser, DummyLark)
    options = captured["options"]
    assert isinstance(options, dict)
    assert options["regex"] is True
    assert options["cache_grammar"] is True
    assert Path(options["cache"]).parent == cache_dir
    assert options["parser"] == "lalr"


def test_parser_cache_path_isolates_version_dimensions(monkeypatch, tmp_path):
    monkeypatch.setattr(parser_api, "_PARSER_CACHE_DIR", tmp_path)
    base = parser_api._parser_cache_path(start="start", propagate_positions=True)
    assert Path(base).parent == tmp_path

    different_start = parser_api._parser_cache_path(start="modulecode", propagate_positions=True)
    different_positions = parser_api._parser_cache_path(start="start", propagate_positions=False)
    assert len({base, different_start, different_positions}) == 3

    monkeypatch.setattr(parser_api, "lark_version", "999.0.0")
    different_lark = parser_api._parser_cache_path(start="start", propagate_positions=True)
    assert different_lark != base


def test_build_lark_parser_tolerates_corrupted_cache_file(monkeypatch, tmp_path):
    cache_dir = tmp_path / "lark-cache"
    cache_dir.mkdir()
    cache_path = str(cache_dir / "corrupt.lark")
    (cache_dir / "corrupt.lark").write_bytes(b"\x00\x01corrupted-not-a-pickle" * 50)

    parser = parser_api.build_lark_parser(start="start", propagate_positions=True)
    assert parser is not None
    # A real cache lookup against the (still corrupt) disk file must not break parsing.
    tree = parser.parse(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*);\n"
    )
    assert tree.data == "start"
    monkeypatch.setattr(parser_api, "_parser_cache_path", lambda **_: cache_path)
    parser2 = parser_api.build_lark_parser(start="start", propagate_positions=True)
    assert parser2 is not None


def test_create_sl_parser_delegates_to_create_parser(monkeypatch):
    sentinel = object()

    def fake_create_parser():
        return sentinel

    monkeypatch.setattr(parser_api, "create_parser", fake_create_parser)

    assert parser_api.create_sl_parser() is sentinel


def test_read_text_with_fallback_accepts_cp1252_bytes(tmp_path):
    source_file = tmp_path / "cp1252.k"
    source_file.write_bytes("Søren".encode("cp1252"))

    assert parser_api.read_text_with_fallback(source_file) == "Søren"


def test_read_text_with_fallback_falls_back_to_latin1(tmp_path):
    source_file = tmp_path / "latin1.bin"
    source_file.write_bytes(b"\x81A")

    assert parser_api.read_text_with_fallback(source_file) == "\x81A"


def test_load_source_text_decodes_compressed_sources_and_emits_debug(monkeypatch, tmp_path):
    events: list[str] = []

    monkeypatch.setattr(parser_api, "_read_text_simple", lambda path: "compressed-body")
    monkeypatch.setattr(parser_api, "is_compressed", lambda text: text == "compressed-body")
    monkeypatch.setattr(
        parser_api,
        "preprocess_source",
        lambda text: SourceDocument("compressed-body", "decoded-source", tuple(range(len("decoded-source")))),
    )

    loaded = parser_api.load_source_text(tmp_path / "Program.s", debug=events.append)

    assert loaded == "decoded-source"
    assert events == [
        f"Parsing file: {tmp_path / 'Program.s'}",
        "Compressed format detected; decoding before parsing",
    ]


def test_parse_source_text_reports_parse_tree_attach_failure(monkeypatch):
    events: list[str] = []
    tree = object()
    basepic = BasePicture(header=ModuleHeader(name="BasePicture", invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0)))

    class FakeParser:
        def parse(self, text: str):
            assert text == "A = 1;"
            return tree

    class FakeTransformer:
        def transform(self, payload):
            assert payload is tree
            return basepic

    def guarded_setattr(self, name, value):
        if name == "parse_tree":
            raise AttributeError("read-only")
        object.__setattr__(self, name, value)

    monkeypatch.setattr(BasePicture, "__setattr__", guarded_setattr)
    result = parser_api.parse_source_text(
        "A = 1;",
        parser=cast(Any, FakeParser()),
        transformer=cast(Any, FakeTransformer()),
        debug=events.append,
    )

    assert result is basepic
    assert events == [
        "Parse OK, transforming with SLTransformer",
        "BasePicture does not allow dynamic attributes; parse tree not attached",
        "Transform result type: BasePicture",
    ]


def test_parse_source_text_raises_when_transformer_returns_non_basepicture(caplog):
    events: list[str] = []
    tree = object()

    class FakeParser:
        def parse(self, text: str):
            assert text == "A = 1;"
            return tree

    class FakeTransformer:
        def transform(self, payload):
            assert payload is tree
            return "not-a-basepicture"

    with (
        caplog.at_level(logging.ERROR, logger="sattline_parser"),
        pytest.raises(
            RuntimeError,
            match="Transform result is not BasePicture",
        ),
    ):
        parser_api.parse_source_text(
            "A = 1;",
            parser=cast(Any, FakeParser()),
            transformer=cast(Any, FakeTransformer()),
            debug=events.append,
        )

    assert events == ["Parse OK, transforming with SLTransformer"]
    record = caplog.records[-1]
    assert record.parser_stage == "transform"
    assert record.parser_path is None
    assert record.parser_context == "Transform result is not BasePicture; check transformer.start()"


def test_parse_source_file_logs_parse_failures_with_path(caplog, tmp_path):
    source_file = tmp_path / "BrokenProgram.s"
    source_file.write_text("IF X THEN", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="sattline_parser"), pytest.raises(UnexpectedToken):
        parser_api.parse_source_file(source_file)

    record = caplog.records[-1]
    assert record.parser_stage == "parse"
    assert record.parser_path == str(source_file)
    assert record.parser_line == 1
    assert record.parser_column is not None
    assert "Unexpected" in record.parser_context


def test_parser_core_create_parser_accepts_legal_comments():
    parser = parser_api.create_parser()
    assert parser is not None
    # The single authoritative parser accepts comments where the grammar
    # permits them (there is no comment-free mode).
    tree = parser.parse(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*);\n"
    )
    assert tree.data == "start"


def test_parser_core_default_parser_is_lru_cached():
    # The default parser is built once and reused.
    parser1 = parser_api._default_parser()
    parser2 = parser_api._default_parser()
    assert parser1 is parser2
