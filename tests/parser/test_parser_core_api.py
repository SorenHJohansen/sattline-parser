# pyright: reportMissingParameterType=false, reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
import getpass
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest
from lark import Token
from lark.exceptions import UnexpectedToken, VisitError

from sattline_parser import source_io as parser_api
from sattline_parser.api import parse_source_file
from sattline_parser.source_document import SourceDocument
from sattline_parser.transformer.sl_transformer import SLTransformer


def test_resolved_grammar_import_raises_when_grammar_file_is_missing(monkeypatch: pytest.MonkeyPatch):
    from sattline_parser.grammar import resolved as resolved_module  # noqa: PLC0415

    module_path = Path(resolved_module.__file__)
    module_name = "sattline_parser.grammar.resolved_missing_grammar_test"
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path == resolved_module.GRAMMAR_PATH:
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


def test_source_text_for_parse_returns_the_text_the_parser_takes(tmp_path):
    code = (
        '"Syntax version 2.23, date: 2026-04-30-00:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-04-30-00:00:00.000, name: Plain"\n'
        "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*);\n"
    )
    source_file = tmp_path / "Plain.s"
    source_file.write_bytes(code.encode("cp1252"))

    assert parser_api.source_text_for_parse(source_file) == code


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


def test_create_parser_uses_regex_and_no_lark_cache_path(monkeypatch, tmp_path):
    """Lark is built without its own cache; the pipeline owns the disk cache."""
    captured: dict[str, object] = {}
    cache_dir = tmp_path / "lark-cache"

    class DummyLark:
        def __init__(self, grammar, **options):
            captured["grammar"] = grammar
            captured["options"] = options

    monkeypatch.setattr(parser_api, "Lark", DummyLark)
    monkeypatch.setattr(parser_api, "_parser_cache_dir", lambda: cache_dir)
    parser = parser_api.create_parser()

    assert isinstance(parser, DummyLark)
    options = captured["options"]
    assert isinstance(options, dict)
    assert options["regex"] is True
    assert options["cache"] is None
    assert options["cache_grammar"] is False
    assert options["parser"] == "lalr"


def test_parser_cache_path_isolates_version_dimensions(monkeypatch, tmp_path):
    monkeypatch.setattr(parser_api, "_parser_cache_dir", lambda: tmp_path)
    base = parser_api._parser_cache_path(start="start", propagate_positions=True)
    assert base is not None and Path(base).parent == tmp_path

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


def test_read_text_cp1252_accepts_cp1252_bytes(tmp_path):
    source_file = tmp_path / "cp1252.k"
    source_file.write_bytes("Søren".encode("cp1252"))

    assert parser_api.read_text_cp1252(source_file) == "Søren"


def test_read_text_cp1252_rejects_bytes_invalid_in_cp1252(tmp_path):
    # 0x81 is undefined in Windows-1252: strict decode, no latin-1/utf-8 fallback
    source_file = tmp_path / "invalid_cp1252.s"
    source_file.write_bytes(b"\x81A")

    with pytest.raises(UnicodeDecodeError):
        parser_api.read_text_cp1252(source_file)


# The real editor accepts a file whose undefined Windows-1252 byte 0x81 sits
# inside a (* ... *) comment. The tolerance is scoped to comment bodies;
# read_text_cp1252 keeps its strict contract.


def test_read_text_cp1252_tolerates_undefined_byte_inside_comment(tmp_path):
    source_file = tmp_path / "comment_byte.s"
    source_file.write_bytes(b'"Syntax version 2.23"\n(* byte \x81 here *)\nA\n')

    decoded = parser_api._decode_source_bytes_for_parse(source_file)

    assert "byte" in decoded and "\ufffd" in decoded


def test_read_text_cp1252_still_rejects_undefined_byte_outside_comment(tmp_path):
    source_file = tmp_path / "code_byte.s"
    source_file.write_bytes(b'"Syntax version 2.23"\nA \x81 B\n')

    with pytest.raises(UnicodeDecodeError):
        parser_api._decode_source_bytes_for_parse(source_file)


def test_read_text_cp1252_strict_helper_is_untouched_by_comment_tolerance(tmp_path):
    """The public strict API must not silently widen, whatever the parse path does."""
    source_file = tmp_path / "comment_byte.s"
    source_file.write_bytes(b"(* \x81 *)\nA\n")

    with pytest.raises(UnicodeDecodeError):
        parser_api.read_text_cp1252(source_file)


def test_read_text_cp1252_rejects_undefined_byte_inside_a_string(tmp_path):
    """A ``(* ... *)`` inside a string is text, so the byte there is not exempt."""
    source_file = tmp_path / "string_byte.s"
    source_file.write_bytes(b'"Syntax version 2.23"\n"(* label \x81 *)"\nA\n')

    with pytest.raises(UnicodeDecodeError):
        parser_api._decode_source_bytes_for_parse(source_file)


def test_read_text_cp1252_tolerates_undefined_byte_in_nested_comment(tmp_path):
    """Comment bodies nest, so the byte stays exempt until the outer ``*)``."""
    source_file = tmp_path / "nested_comment.s"
    source_file.write_bytes(b'"Syntax version 2.23"\n(* outer (* inner *) byte \x81 here *)\nA\n')

    decoded = parser_api._decode_source_bytes_for_parse(source_file)

    assert "outer" in decoded
    assert "inner" in decoded
    assert "\ufffd" in decoded


def test_read_text_cp1252_handles_doubled_quotes_before_a_comment(tmp_path):
    """A doubled quote is an escaped quote, so the literal does not end early."""
    source_file = tmp_path / "doubled_quote.s"
    source_file.write_bytes(b'"Syntax version 2.23"\n"say ""(*)"" here" (* byte \x81 *)\nA\n')

    decoded = parser_api._decode_source_bytes_for_parse(source_file)

    assert 'say ""(*)"" here' in decoded
    assert "\ufffd" in decoded


def test_load_source_text_decodes_compressed_sources_and_emits_debug(monkeypatch, tmp_path):
    events: list[str] = []

    (tmp_path / "Program.s").write_text("compressed-body")
    monkeypatch.setattr(parser_api, "is_coded", lambda data: False)
    monkeypatch.setattr(parser_api, "read_text_cp1252", lambda path: "compressed-body")
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
    assert "unexpected" in record.parser_context
    assert "Token(" not in record.parser_context


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


def test_read_text_cp1252_keeps_strict_decode_after_an_unterminated_string(tmp_path):
    """An unterminated literal leaves no reliable boundary, so strictness returns."""
    source_file = tmp_path / "unterminated_string.s"
    source_file.write_bytes(b'"Syntax version 2.23"\n(* byte \x81 *)\n"unterminated')

    decoded = parser_api._decode_source_bytes_for_parse(source_file)

    assert "\ufffd" in decoded
    assert "unterminated" in decoded


def test_parser_cache_is_disabled_without_a_private_directory(monkeypatch):
    monkeypatch.setattr(parser_api, "_parser_cache_dir", lambda: None)

    assert parser_api._parser_cache_path(start="start", propagate_positions=True) is None


def test_build_lark_parser_disables_grammar_cache_without_a_cache_path(monkeypatch):
    monkeypatch.setattr(parser_api, "_parser_cache_path", lambda **_: None)

    parser = parser_api.build_lark_parser()

    assert parser.options.cache is None


def test_private_cache_dir_creates_a_private_directory(tmp_path):
    directory = tmp_path / "nested" / "lark-cache"

    assert parser_api.private_cache_dir(directory) == directory
    if os.name == "posix":
        # Windows has no POSIX permission bits; chmod only toggles the read-only
        # attribute, so the mode is not asserted there.
        assert directory.stat().st_mode & 0o777 == 0o700


def test_private_cache_dir_tightens_existing_permissions(tmp_path):
    directory = tmp_path / "lark-cache"
    directory.mkdir()
    directory.chmod(0o755)

    assert parser_api.private_cache_dir(directory) == directory
    if os.name == "posix":
        assert directory.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner check")
def test_private_cache_dir_rejects_when_no_owner_check_is_available(monkeypatch, tmp_path):
    # No platform privacy check applies, so the directory cannot be proven
    # private. The cache is an optimisation and is disabled instead of trusted.
    monkeypatch.setattr(parser_api, "_getuid", None)
    directory = tmp_path / "shared-cache"
    directory.mkdir()
    directory.chmod(0o777)

    assert parser_api.private_cache_dir(directory) is None


def test_private_cache_dir_rejects_when_the_windows_check_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(parser_api, "_IS_WINDOWS", True)
    monkeypatch.setattr(parser_api, "windows_directory_is_private", lambda path: False)

    assert parser_api.private_cache_dir(tmp_path / "cache") is None


def test_private_cache_dir_accepts_when_the_windows_check_proves_privacy(monkeypatch, tmp_path):
    monkeypatch.setattr(parser_api, "_IS_WINDOWS", True)
    seen: list[Path] = []

    def private(path: Path) -> bool:
        seen.append(path)
        return True

    monkeypatch.setattr(parser_api, "windows_directory_is_private", private)
    directory = tmp_path / "cache"

    assert parser_api.private_cache_dir(directory) == directory
    assert seen == [directory]


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner check")
def test_private_cache_dir_rejects_a_foreign_owner(monkeypatch, tmp_path):
    # Driven through the resolved uid callable so the case runs everywhere: the
    # current user never owns the synthetic uid.
    monkeypatch.setattr(parser_api, "_getuid", lambda: -1)

    assert parser_api.private_cache_dir(tmp_path / "lark-cache") is None


def test_private_cache_dir_gives_up_when_it_cannot_be_created(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")

    assert parser_api.private_cache_dir(blocker / "lark-cache") is None


def test_private_directory_gives_up_when_creation_raises(tmp_path, monkeypatch):
    def failing_mkdir(self, mode=0o777, parents=False, exist_ok=False):
        raise OSError("boom")

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    assert parser_api._private_directory(tmp_path / "cache") is None


def test_private_directory_gives_up_when_lstat_fails(tmp_path, monkeypatch):
    def failing_lstat(self):
        raise OSError("boom")

    monkeypatch.setattr(Path, "lstat", failing_lstat)

    assert parser_api._private_directory(tmp_path / "cache") is None


@pytest.mark.skipif(os.name != "posix", reason="Windows has no POSIX permission bits")
def test_private_directory_gives_up_when_chmod_fails(tmp_path, monkeypatch):
    directory = tmp_path / "cache"
    directory.mkdir()
    directory.chmod(0o755)

    def failing_chmod(self, mode, *, follow_symlinks=True):
        raise OSError("boom")

    monkeypatch.setattr(Path, "chmod", failing_chmod)

    assert parser_api._private_directory(directory) is None


@pytest.mark.skipif(os.name != "posix", reason="Windows has no POSIX permission bits")
def test_private_directory_gives_up_when_it_stays_too_open(tmp_path, monkeypatch):
    directory = tmp_path / "cache"
    directory.mkdir()
    directory.chmod(0o755)

    def no_op_chmod(self, mode, *, follow_symlinks=True):
        return None

    monkeypatch.setattr(Path, "chmod", no_op_chmod)

    assert parser_api._private_directory(directory) is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner check")
def test_parser_cache_dir_disables_a_cache_under_a_foreign_parent(monkeypatch, tmp_path):
    """A predictable name under the shared temp directory is attacker-reachable."""
    monkeypatch.setattr(parser_api, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(parser_api, "_getuid", lambda: -1)

    assert parser_api._parser_cache_dir() is None


def test_parser_cache_dir_validates_the_per_user_parent(monkeypatch, tmp_path):
    monkeypatch.setattr(parser_api, "gettempdir", lambda: str(tmp_path))
    root = tmp_path / f"sattline-parser-{parser_api._cache_owner_token()}"
    root.write_text("not a directory", encoding="utf-8")

    assert parser_api._parser_cache_dir() is None


@pytest.mark.skipif(os.name != "posix", reason="symlink creation needs POSIX permissions")
def test_parser_cache_dir_rejects_a_symlinked_per_user_directory(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    root = tmp_path / f"sattline-parser-{parser_api._cache_owner_token()}"
    root.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(parser_api, "gettempdir", lambda: str(tmp_path))

    assert parser_api._parser_cache_dir() is None
    assert not (target / "lark-cache").exists()


def test_parser_cache_dir_creates_a_private_parent_and_child(monkeypatch, tmp_path):
    monkeypatch.setattr(parser_api, "gettempdir", lambda: str(tmp_path))

    directory = parser_api._parser_cache_dir()

    assert directory is not None
    assert directory.name == "lark-cache"
    if os.name == "posix":
        assert directory.stat().st_mode & 0o777 == 0o700
        assert directory.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name != "posix", reason="symlink creation needs POSIX permissions")
def test_private_cache_dir_rejects_a_symlinked_directory(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    assert parser_api.private_cache_dir(link) is None


@pytest.mark.skipif(os.name != "posix", reason="Windows has no POSIX permission bits")
def test_a_read_only_directory_check_never_creates_or_tightens(tmp_path):
    """A reader validates a directory; only a writer may create or chmod one."""
    missing = tmp_path / "missing"
    assert parser_api.private_cache_dir(missing, create=False) is None
    assert not missing.exists()

    directory = tmp_path / "cache"
    directory.mkdir()
    directory.chmod(0o755)
    assert parser_api.private_cache_dir(directory, create=False) is None
    assert directory.stat().st_mode & 0o777 == 0o755


def test_cache_owner_token_falls_back_without_getuid(monkeypatch):
    monkeypatch.setattr(parser_api, "_getuid", None)

    assert parser_api._cache_owner_token() == getpass.getuser()


def test_cache_owner_token_uses_the_uid_when_available(monkeypatch):
    monkeypatch.setattr(parser_api, "_getuid", lambda: 4242)

    assert parser_api._cache_owner_token() == "4242"


def test_decode_cp1252_tolerant_passes_clean_text_straight_through():
    assert parser_api._decode_cp1252_comments_tolerant(b"plain text") == "plain text"


def test_read_text_cp1252_rejects_undefined_byte_after_a_closed_comment(tmp_path):
    source_file = tmp_path / "after_comment.s"
    source_file.write_bytes(b'"Syntax version 2.23"\n(* ok *)\nA \x81 B\n')

    with pytest.raises(UnicodeDecodeError):
        parser_api._decode_source_bytes_for_parse(source_file)


#: A module header with two ``Layer_`` arguments. The transformer rejects the
#: second one, so the source parses and fails in the transform stage, which is
#: exactly where Lark wraps a rule failure in ``VisitError``.
_DUPLICATE_CLAUSE_SOURCE = """"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: Duplicate"

BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 Layer_ = 1 Layer_ = 2 ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""


class _RejectingTransformer(SLTransformer):
    """Rejects the duplicate clause the way the transformer's own guard does.

    The guard itself belongs to the transformer, so this stub keeps the
    parse-level contract (Lark wraps a rule failure in ``VisitError`` and
    ``source_io`` must unwrap it) verifiable without depending on which clauses
    the guard currently covers.
    """

    def argument(self, items: list[object]) -> NoReturn:
        raise ValueError("module header has more than one Layer_ argument")


class _RaisingUnexpectedInputTransformer(SLTransformer):
    """Raises a parse error from a rule, as a rejected clause could."""

    def argument(self, items: list[object]) -> NoReturn:
        raise UnexpectedToken(Token("NAME", "Layer_"), ["')'"])


class _DefectiveTransformer(SLTransformer):
    """Raises a parser defect, which must not be reported as a broken source."""

    def argument(self, items: list[object]) -> NoReturn:
        raise RuntimeError("transformer defect")


def test_a_transformer_rejection_is_raised_as_its_own_error():
    with pytest.raises(ValueError, match="more than one Layer_ argument") as exc_info:
        parser_api.parse_source_text(
            _DUPLICATE_CLAUSE_SOURCE,
            transformer=_RejectingTransformer(),
            log_failures=False,
        )

    assert type(exc_info.value) is ValueError
    cause = exc_info.value.__cause__
    assert isinstance(cause, VisitError)
    assert cause.orig_exc is exc_info.value


def test_a_transformer_parse_error_is_unwrapped_from_visit_error():
    with pytest.raises(UnexpectedToken) as exc_info:
        parser_api.parse_source_text(
            _DUPLICATE_CLAUSE_SOURCE,
            transformer=_RaisingUnexpectedInputTransformer(),
            log_failures=False,
        )

    assert isinstance(exc_info.value.__cause__, VisitError)


def test_a_transformer_defect_stays_wrapped_in_visit_error():
    """A ``RuntimeError`` marks a parser defect, so it is never a finding."""
    with pytest.raises(VisitError) as exc_info:
        parser_api.parse_source_text(
            _DUPLICATE_CLAUSE_SOURCE,
            transformer=_DefectiveTransformer(),
            log_failures=False,
        )

    assert isinstance(exc_info.value.orig_exc, RuntimeError)
