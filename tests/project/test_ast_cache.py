# pyright: reportPrivateUsage=false
"""Unit tests for the parser-owned per-file AST cache (``project/ast_cache.py``)."""

from __future__ import annotations

import hashlib
import hmac
import os
import pickle
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.__version__ import __version__
from sattline_parser.api import parse_source_file
from sattline_parser.grammar import constants as const
from sattline_parser.grammar.resolved import grammar_fingerprint
from sattline_parser.models.ast_model import (
    BasePicture,
    GraphObject,
    InteractObject,
    ModuleDef,
    ModuleHeader,
    SourceSpan,
)
from sattline_parser.models.clauses import (
    AssignClause,
    ClippingClause,
    ColourSpec,
    EnableClause,
    ModuleArguments,
    TailedClause,
)
from sattline_parser.models.tails import LitStringTail, VarTail
from sattline_parser.project import FILE_AST_CACHE_VERSION, FileASTCache
from sattline_parser.project.ast_cache import (
    _CODE_FINGERPRINT_SOURCES,
    _PICKLE_CACHE_MAGIC,
    _PICKLE_HMAC_KEY_NAME,
    SourceSnapshot,
    _as_data_dict,
    _code_fingerprint,
    _code_path_key,
    _load_or_create_pickle_hmac_key,
    _load_pickle_payload,
    _matches_source_identity,
    _read_pickle_hmac_key,
    _read_signed_pickle_envelope,
    _remove_file,
    _safe_stat,
    _save_pickle_payload,
    _stored_source_exists,
    _temp_file_is_abandoned,
    _temp_path_for,
    source_snapshot,
)

_AC_PATH = "sattline_parser.project.ast_cache"

_MINIMAL_SOURCE = """"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: MinimalProgram"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""


def _write_code(tmp_path: Path, name: str = "Prog.s") -> Path:
    path = tmp_path / name
    path.write_text(_MINIMAL_SOURCE, encoding="utf-8")
    return path


def _picture(code_path: Path) -> BasePicture:
    return parse_source_file(code_path)


def _key_path(cache: FileASTCache) -> Path:
    return cache.cache_dir / _PICKLE_HMAC_KEY_NAME


def test_envelope_rejects_wrong_magic() -> None:
    assert _read_signed_pickle_envelope(b"nope") == (None, b"")


def test_envelope_rejects_missing_separator() -> None:
    assert _read_signed_pickle_envelope(_PICKLE_CACHE_MAGIC + b"not-here") == (None, b"")


def test_envelope_rejects_wrong_signature_length() -> None:
    for lengths in (1, 63, 65):
        signature = b"a" * lengths
        envelope = _PICKLE_CACHE_MAGIC + signature + b"\npayload"
        assert _read_signed_pickle_envelope(envelope) == (None, b"")


def test_typed_tail_nodes_survive_a_pickle_round_trip() -> None:
    """The AST cache pickles the model; the new frozen tail/clause nodes must round-trip.

    ``FILE_AST_CACHE_VERSION`` is bumped whenever the model shape changes, so an
    old envelope is never read as if it held the current nodes.
    """
    corner = VarTail("in", "Corner")
    span = SourceSpan(start=3, end=9, line=1, column=4)
    module_def = ModuleDef(
        clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (corner,)),
        graph_objects=[
            GraphObject(
                type=const.GRAMMAR_VALUE_TEXTOBJECT,
                properties={
                    const.KEY_COLOURS: [
                        ColourSpec(
                            "outline",
                            width=TailedClause(const.GRAMMAR_VALUE_WIDTH_KEY, 2, VarTail("in", "WidthTail")),
                        )
                    ],
                    const.KEY_COORDS: ((-1.0, 1.0), (1.0, -1.0)),
                },
                span=span,
            )
        ],
        interact_objects=[
            InteractObject(
                type=const.GRAMMAR_VALUE_COMBUT,
                properties={const.KEY_ASSIGNS: [AssignClause("Variable", 0, VarTail("out", "AssignTail"))]},
                span=span,
            )
        ],
        span=span,
    )
    picture = BasePicture(
        header=ModuleHeader(
            name="BasePicture",
            invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
            arguments=ModuleArguments(enable=EnableClause(True, VarTail("in", "EnableVar"))),
            invoke_coord_tails=[VarTail("out", LitStringTail("LitString", "Symbol"))],
        ),
        position=(1.0, 2.0, 3.0, 4.0, 5.0),
        moduledefs=[module_def],
    )

    restored = pickle.loads(pickle.dumps(picture))

    assert restored == picture
    assert restored.header.invoke_coord_tails == [VarTail("out", LitStringTail("LitString", "Symbol"))]
    assert restored.header.invoke_coord == (0.0, 0.0, 0.0, 1.0, 1.0)
    assert restored.position == (1.0, 2.0, 3.0, 4.0, 5.0)
    assert restored.moduledefs[0].clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))
    assert restored.moduledefs[0].clipping_tails == (corner,)
    assert restored.moduledefs[0].span == span
    assert restored.moduledefs[0].graph_objects[0].span == span
    assert restored.moduledefs[0].interact_objects[0].span == span
    assert FILE_AST_CACHE_VERSION == 11


def test_envelope_round_trip() -> None:
    payload = b"hello"
    signature = hashlib.sha256(payload).hexdigest().encode("ascii")
    envelope = _PICKLE_CACHE_MAGIC + signature + b"\n" + payload
    assert _read_signed_pickle_envelope(envelope) == (signature.decode("ascii"), payload)


def test_envelope_rejects_non_ascii_signature() -> None:
    envelope = _PICKLE_CACHE_MAGIC + b"\xff" * 64 + b"\npayload"
    assert _read_signed_pickle_envelope(envelope) == (None, b"")


def test_as_data_dict() -> None:
    assert _as_data_dict({"a": 1}) == {"a": 1}
    assert _as_data_dict("x") is None


def test_remove_file(tmp_path: Path) -> None:
    target = tmp_path / "gone"
    target.write_text("x", encoding="utf-8")
    assert _remove_file(target) is True
    assert not target.exists()
    with patch(f"{_AC_PATH}.Path.unlink", side_effect=OSError("boom")):
        assert _remove_file(target) is False


def test_safe_stat(tmp_path: Path) -> None:
    assert _safe_stat(tmp_path / "missing") is None
    assert _safe_stat(tmp_path) is not None


def test_matches_source_identity_is_false_when_the_read_fails(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_text("abc", encoding="utf-8")
    stat_result = path.stat()

    with patch(f"{_AC_PATH}.Path.read_bytes", side_effect=OSError("boom")):
        assert not _matches_source_identity(
            path,
            mtime_ns=stat_result.st_mtime_ns,
            size=stat_result.st_size,
            digest=hashlib.sha256(b"abc").hexdigest(),
        )


def test_source_snapshot_is_none_when_the_read_fails(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_text("abc", encoding="utf-8")

    with patch(f"{_AC_PATH}.Path.read_bytes", side_effect=OSError("boom")):
        assert source_snapshot(path) is None


def test_matches_source_identity(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_text("abc", encoding="utf-8")
    stat_result = path.stat()
    digest = hashlib.sha256(b"abc").hexdigest()
    assert _matches_source_identity(path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size, digest=digest)
    assert not _matches_source_identity(
        path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size, digest=hashlib.sha256(b"abd").hexdigest()
    )
    assert not _matches_source_identity(
        path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size + 1, digest=digest
    )
    path.unlink()
    assert not _matches_source_identity(path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size, digest=digest)
    assert not _matches_source_identity(path, mtime_ns="x", size=stat_result.st_size, digest=digest)
    assert not _matches_source_identity(path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size, digest=1)


def test_read_pickle_hmac_key(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert _read_pickle_hmac_key(missing) is None
    short = tmp_path / "short"
    short.write_bytes(b"123")
    assert _read_pickle_hmac_key(short) is None
    key = tmp_path / "key"
    key.write_bytes(b"k" * 32)
    assert _read_pickle_hmac_key(key) == b"k" * 32


def test_load_or_create_hmac_key_creates_then_reuses(tmp_path: Path) -> None:
    first = _load_or_create_pickle_hmac_key(tmp_path)
    assert first is not None and len(first) == 32
    assert _load_or_create_pickle_hmac_key(tmp_path) == first
    if os.name == "posix":
        assert _key_stat_mode_is_private(tmp_path)


def _key_stat_mode_is_private(directory: Path) -> bool:
    key_path = directory / _PICKLE_HMAC_KEY_NAME
    return (key_path.stat().st_mode & 0o777) == 0o600


def test_load_or_create_hmac_key_recreates_invalid_existing(tmp_path: Path) -> None:
    key_path = tmp_path / _PICKLE_HMAC_KEY_NAME
    key_path.write_bytes(b"toolong")
    created = _load_or_create_pickle_hmac_key(tmp_path)
    assert created is not None and len(created) == 32
    assert key_path.read_bytes() == created


def test_load_or_create_hmac_key_remove_failure(tmp_path: Path) -> None:
    key_path = tmp_path / _PICKLE_HMAC_KEY_NAME
    key_path.write_bytes(b"toolong")
    with patch(f"{_AC_PATH}.Path.unlink", side_effect=OSError("boom")):
        assert _load_or_create_pickle_hmac_key(tmp_path) is None


def test_load_or_create_hmac_key_race_returns_concurrent_key(tmp_path: Path) -> None:
    def _race(path: str, flags: int, mode: int) -> int:
        Path(path).write_bytes(b"y" * 32)
        raise FileExistsError

    with patch(f"{_AC_PATH}.os.open", side_effect=_race):
        result = _load_or_create_pickle_hmac_key(tmp_path)
    assert result == b"y" * 32


def test_load_or_create_hmac_key_open_oserror(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.os.open", side_effect=OSError("boom")):
        assert _load_or_create_pickle_hmac_key(tmp_path) is None


def test_load_or_create_hmac_key_write_oserror(tmp_path: Path) -> None:
    key_path = tmp_path / _PICKLE_HMAC_KEY_NAME
    with patch(f"{_AC_PATH}.os.fsync", side_effect=OSError("boom")):
        assert _load_or_create_pickle_hmac_key(tmp_path) is None
    assert not key_path.exists()


def test_load_pickle_payload_missing_file(tmp_path: Path) -> None:
    assert _load_pickle_payload(tmp_path / "missing.pickle") is None


def test_load_pickle_payload_rejects_wrong_signature(tmp_path: Path) -> None:
    target = tmp_path / "e.pickle"
    target.write_bytes(_PICKLE_CACHE_MAGIC + b"a" * 64 + b"\n" + b"payload")
    assert _load_pickle_payload(target) is None


def test_load_pickle_payload_no_key(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.os.open", side_effect=OSError("boom")):
        _load_or_create_pickle_hmac_key(tmp_path)
        target = tmp_path / "e.pickle"
        target.write_bytes(_PICKLE_CACHE_MAGIC + b"a" * 64 + b"\npayload")
        assert _load_pickle_payload(target) is None


def test_load_pickle_payload_hmac_mismatch_and_unpickle_error(tmp_path: Path) -> None:
    key = _load_or_create_pickle_hmac_key(tmp_path)
    assert key is not None
    for index, payload_body in enumerate((b"payload", b"garbage")):
        if index == 0:
            signature = hmac.new(key, payload_body, hashlib.sha256).hexdigest()
            signature = ("0" + signature[1:]).encode("ascii")
        else:
            signature = hmac.new(key, payload_body, hashlib.sha256).hexdigest().encode("ascii")
        target = tmp_path / f"e{index}.pickle"
        target.write_bytes(_PICKLE_CACHE_MAGIC + signature + b"\n" + payload_body)
        assert _load_pickle_payload(target) is None


def test_save_pickle_payload_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "e.pickle"
    _save_pickle_payload(target, {"version": 1, "value": "ok"})
    assert _load_pickle_payload(target) == {"version": 1, "value": "ok"}


def test_save_pickle_payload_replace_failure(tmp_path: Path) -> None:
    target = tmp_path / "e.pickle"
    with patch(f"{_AC_PATH}.os.replace", side_effect=OSError("boom")), pytest.raises(OSError, match="boom"):
        _save_pickle_payload(target, {"version": 1})
    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_temp_paths_are_unique_per_write(tmp_path: Path) -> None:
    """Two writers must never share a temporary path."""
    target = tmp_path / "e.pickle"

    assert _temp_path_for(target) != _temp_path_for(target)


def test_save_pickle_payload_key_failure(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.os.open", side_effect=OSError("boom")), pytest.raises(OSError, match="pickle HMAC key"):
        _save_pickle_payload(tmp_path / "e.pickle", {"version": 1})


def test_load_missing_entry_returns_none(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    assert cache.enabled
    assert cache.load(code_path, "draft") is None


def test_cache_is_disabled_when_the_root_is_not_owned_by_this_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code_path = _write_code(tmp_path)
    monkeypatch.setattr("sattline_parser.source_io._getuid", lambda: -1)

    cache = FileASTCache(tmp_path / "cache")

    assert not cache.enabled
    assert not cache.cache_dir.exists()
    cache.save(code_path, "draft", _picture(code_path))
    assert cache.load(code_path, "draft") is None
    assert cache.prune_stale_entries() == 0
    assert cache._prune_temporary_files() == 0
    assert cache.drain_startup_pruned_entries() == 0


def test_cache_is_disabled_when_the_owned_root_cannot_be_made_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code_path = _write_code(tmp_path)
    monkeypatch.setattr("sattline_parser.source_io._getuid", lambda: -1)
    (tmp_path / "cache").mkdir()

    cache = FileASTCache(tmp_path / "cache")

    assert not cache.enabled
    assert not cache.cache_dir.exists()
    assert cache.load(code_path, "draft") is None


def test_cache_is_disabled_when_the_subdirectory_is_not_a_directory(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    (cache_root / "file_ast").write_text("not a directory", encoding="utf-8")

    cache = FileASTCache(cache_root)

    assert not cache.enabled
    assert cache.load(_write_code(tmp_path), "draft") is None


def test_startup_prune_removes_abandoned_temp_when_identity_matches(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    abandoned = cache.cache_dir / "leftover.pickle.tmp"
    abandoned.write_bytes(b"x")
    old = time.time() - 7200
    os.utime(abandoned, (old, old))

    restarted = FileASTCache(tmp_path)

    assert restarted.drain_startup_pruned_entries() == 1
    assert not abandoned.exists()


def test_prune_temporary_files_missing_directory(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    shutil.rmtree(cache.cache_dir)
    assert cache._prune_temporary_files() == 0


def test_startup_prune_survives_an_undecodable_identity_marker(tmp_path: Path) -> None:
    """A marker whose bytes are not ASCII means "unknown identity", not a crash."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    (cache.cache_dir / ".parser-identity").write_bytes(b"\xff\xfe\x80")

    restarted = FileASTCache(tmp_path)

    assert restarted.load(code_path, "draft") == _picture(code_path)
    assert (cache.cache_dir / ".parser-identity").read_text(encoding="ascii") == restarted._identity_text()


def test_startup_prune_is_skipped_when_identity_marker_matches(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))

    with patch(f"{_AC_PATH}._load_pickle_payload", side_effect=AssertionError("must not unpickle at startup")):
        restarted = FileASTCache(tmp_path)

    assert restarted.drain_startup_pruned_entries() == 0
    assert restarted.load(code_path, "draft") == _picture(code_path)


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    assert cache.drain_startup_pruned_entries() == 0
    ast = _picture(code_path)
    cache.save(code_path, "draft", ast)
    cached = cache.load(code_path, "draft")
    assert cached is not None
    assert cached == ast


def test_load_rejects_mode_mismatch(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    assert cache.load(code_path, "official") is None


def test_load_rejects_version_mismatch(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    stat_result = code_path.stat()
    _save_pickle_payload(
        cache._path(code_path, "draft"),
        {
            "version": FILE_AST_CACHE_VERSION + 1,
            "meta": {
                "path": str(code_path),
                "mode": "draft",
                "parser_version": __version__,
                "grammar": grammar_fingerprint(),
                "code": _code_fingerprint(),
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
                "sha256": hashlib.sha256(code_path.read_bytes()).hexdigest(),
            },
            "ast": _picture(code_path),
        },
    )
    assert cache.load(code_path, "draft") is None


def test_cache_key_includes_package_version_grammar_and_code(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    key = cache._key(code_path, "draft")

    with patch(f"{_AC_PATH}.__version__", "0.0.0"):
        assert cache._key(code_path, "draft") != key
    with patch(f"{_AC_PATH}.grammar_fingerprint", return_value="0" * 64):
        assert cache._key(code_path, "draft") != key
    with patch(f"{_AC_PATH}._code_fingerprint", return_value="0" * 64):
        assert cache._key(code_path, "draft") != key


@pytest.mark.parametrize(
    ("field", "value"),
    [("parser_version", "0.0.0"), ("grammar", "0" * 64), ("code", "0" * 64)],
)
def test_load_rejects_identity_mismatch(tmp_path: Path, field: str, value: str) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    stat_result = code_path.stat()
    meta: dict[str, object] = {
        "path": str(code_path),
        "mode": "draft",
        "parser_version": __version__,
        "grammar": grammar_fingerprint(),
        "code": _code_fingerprint(),
        "mtime_ns": stat_result.st_mtime_ns,
        "size": stat_result.st_size,
    }
    meta[field] = value
    _save_pickle_payload(
        cache._path(code_path, "draft"),
        {
            "version": FILE_AST_CACHE_VERSION,
            "meta": meta,
            "ast": _picture(code_path),
        },
    )

    assert cache.load(code_path, "draft") is None


def test_load_rejects_meta_and_payload_shape(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    stat_result = code_path.stat()
    ast = _picture(code_path)

    def _payload(mode: str, **override: object) -> dict[str, object]:
        data: dict[str, object] = {
            "version": FILE_AST_CACHE_VERSION,
            "meta": {
                "path": str(code_path),
                "mode": mode,
                "parser_version": __version__,
                "grammar": grammar_fingerprint(),
                "code": _code_fingerprint(),
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
                "sha256": hashlib.sha256(code_path.read_bytes()).hexdigest(),
            },
            "ast": ast,
        }
        data.update(override)
        return data

    modes = ("good", "bad-meta", "bad-ast", "bad-path", "bad-mode", "not-mapping", "version")
    cases = {
        "good": _payload("good"),
        "bad-meta": _payload("bad-meta", meta=42),
        "bad-ast": _payload("bad-ast", ast="not-a-picture"),
        "bad-path": _payload(
            "bad-path",
            meta={
                "path": "/wrong",
                "mode": "bad-path",
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
                "sha256": hashlib.sha256(code_path.read_bytes()).hexdigest(),
            },
        ),
        "bad-mode": _payload(
            "bad-mode",
            meta={
                "path": str(code_path),
                "mode": "WRONG",
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
                "sha256": hashlib.sha256(code_path.read_bytes()).hexdigest(),
            },
        ),
    }
    assert len(modes) == len(cases) + 2
    for mode, payload in cases.items():
        _save_pickle_payload(cache._path(code_path, mode), payload)
    _save_pickle_payload(cache._path(code_path, "not-mapping"), ["not", "a", "dict"])
    _save_pickle_payload(cache._path(code_path, "version"), _payload("version", version=99))

    assert cache.load(code_path, "good") == ast
    for mode in ("bad-meta", "bad-ast", "bad-path", "bad-mode", "not-mapping", "version"):
        assert cache.load(code_path, mode) is None


def test_load_rejects_stat_change(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    ast = _picture(code_path)
    cache.save(code_path, "draft", ast)
    assert cache.load(code_path, "draft") == ast
    code_path.write_text(_MINIMAL_SOURCE + "\n", encoding="utf-8")
    assert cache.load(code_path, "draft") is None


def test_a_graph_object_geometry_fixture_round_trips_through_the_cache(tmp_path: Path) -> None:
    """Every polygon point and text clause survives the signed pickle envelope."""
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "valid" / "GraphObjectGeometry.s"
    cache = FileASTCache(tmp_path / "cache")
    picture = parse_source_file(fixture)

    cache.save(fixture, "draft", picture)

    restored = cache.load(fixture, "draft")
    assert restored == picture
    assert restored is not None
    polygon = next(obj for obj in restored.moduledefs[0].graph_objects if obj.type == "PolygonObject")
    points = polygon.properties.get("points") or []
    assert len(points) == 5


def test_load_rejects_new_bytes_with_an_unchanged_stat(tmp_path: Path) -> None:
    """A same-size edit inside the mtime granularity must not be served as a hit."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    stat_result = code_path.stat()
    original = _MINIMAL_SOURCE.encode("utf-8")
    edited = original.replace(b"name: MinimalProgram", b"name: MinimalPrograx")
    assert len(edited) == len(original)
    code_path.write_bytes(edited)
    os.utime(code_path, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns))
    restored = code_path.stat()
    assert (restored.st_mtime_ns, restored.st_size) == (stat_result.st_mtime_ns, stat_result.st_size)

    assert cache.load(code_path, "draft") is None


def test_save_keeps_an_entry_when_only_the_mtime_moved(tmp_path: Path) -> None:
    """Identical bytes under a restored mtime are the same revision."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    snapshot = source_snapshot(code_path)
    assert snapshot is not None
    stat_result = code_path.stat()
    os.utime(code_path, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns - 1_000_000))

    cache.save(code_path, "draft", _picture(code_path), snapshot=snapshot)

    assert cache.load(code_path, "draft") is not None


def test_save_refuses_a_snapshot_the_source_no_longer_matches(tmp_path: Path) -> None:
    """A body parsed from an older revision must not be stored as current."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)

    cache.save(code_path, "draft", _picture(code_path), snapshot=SourceSnapshot(mtime_ns=0, size=0, sha256="0" * 64))

    assert cache.load(code_path, "draft") is None


def test_save_with_the_snapshot_the_parse_started_from_writes_the_entry(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    snapshot = source_snapshot(code_path)
    assert snapshot is not None

    cache.save(code_path, "draft", _picture(code_path), snapshot=snapshot)

    assert cache.load(code_path, "draft") is not None


def test_source_snapshot_is_none_for_a_missing_file(tmp_path: Path) -> None:
    assert source_snapshot(tmp_path / "missing.s") is None


def test_load_key_normalizes_path_spelling(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    ast = _picture(code_path)
    cache.save(code_path, "draft", ast)
    alternate = tmp_path / ".." / tmp_path.name / code_path.name
    assert alternate.resolve() == code_path.resolve()
    assert cache.load(alternate, "draft") == ast


def test_code_path_key_resolve_failure(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    with patch(f"{_AC_PATH}.Path.resolve", side_effect=OSError("boom")):
        assert _code_path_key(code_path) == str(code_path)


def test_load_rejects_tampered_and_garbage_envelope(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    ast = _picture(code_path)
    cache.save(code_path, "draft", ast)
    assert cache.load(code_path, "draft") == ast

    good = cache._path(code_path, "draft").read_bytes()
    tampered = good[:-2] + b"\x00\x00"
    cache._path(code_path, "draft").write_bytes(tampered)
    assert cache.load(code_path, "draft") is None

    _save_pickle_payload(cache._path(code_path, "official"), "junk")
    assert cache.load(code_path, "official") is None


def test_load_with_no_key_missing_returns_none(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    _key_path(cache).unlink()
    with patch(f"{_AC_PATH}.os.open", side_effect=OSError("boom")):
        assert cache.load(code_path, "draft") is None


def test_save_no_op_when_code_file_missing(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    ast = _picture(code_path)
    code_path.unlink()
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", ast)
    assert not list(cache.cache_dir.glob("*.pickle"))


def test_prune_stale_entries(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    stale = cache.cache_dir / "stale.pickle"
    _save_pickle_payload(stale, {"version": FILE_AST_CACHE_VERSION + 7, "ast": 1})
    old_identity = cache.cache_dir / "old-identity.pickle"
    _save_pickle_payload(
        old_identity,
        {
            "version": FILE_AST_CACHE_VERSION,
            "meta": {"parser_version": "0.0.0", "grammar": grammar_fingerprint()},
        },
    )
    foreign = cache.cache_dir / "foreign.pickle"
    foreign.write_bytes(b"no magic")
    tmp = cache.cache_dir / "leftover.pickle.tmp"
    tmp.write_bytes(b"x")
    abandoned = time.time() - 7200
    os.utime(tmp, (abandoned, abandoned))
    subdir = cache.cache_dir / "subdir"
    subdir.mkdir()

    removed = cache.prune_stale_entries()

    assert removed == 4
    assert cache.load(code_path, "draft") is not None
    assert not stale.exists()
    assert not old_identity.exists()
    assert not foreign.exists()
    assert not tmp.exists()
    assert subdir.is_dir()


def test_prune_keeps_a_temporary_file_a_writer_may_still_own(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    inflight = cache.cache_dir / "inflight.pickle.tmp"
    inflight.write_bytes(b"x")

    assert cache.prune_stale_entries() == 0
    assert inflight.exists()


def test_prune_missing_directory(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    shutil.rmtree(cache.cache_dir)
    assert cache.prune_stale_entries() == 0


def test_prune_empty_dir(tmp_path: Path) -> None:
    (tmp_path / "file_ast").mkdir(parents=True)
    cache = FileASTCache(tmp_path)
    assert cache.prune_stale_entries() == 0


def test_drain_startup_pruned_entries(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    (cache_dir / "file_ast").mkdir(parents=True)
    (cache_dir / "file_ast" / "stale.pickle").write_bytes(b"x")
    cache = FileASTCache(cache_dir)
    assert cache.drain_startup_pruned_entries() == 1
    assert cache.drain_startup_pruned_entries() == 0


def test_temp_file_without_a_stat_is_abandoned(tmp_path: Path) -> None:
    path = tmp_path / "gone.pickle.tmp"

    assert _temp_file_is_abandoned(path)


def test_code_fingerprint_covers_the_decoding_and_name_modules() -> None:
    """A fix in decoding, span remapping, or name folding must invalidate an AST."""
    assert {"preprocessing", "source_io.py", "source_document.py", "names.py"} <= set(_CODE_FINGERPRINT_SOURCES)


def test_code_fingerprint_hashes_a_standalone_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "names.py"
    source.write_text("FOLD = 1\n", encoding="utf-8")
    monkeypatch.setattr(f"{_AC_PATH}._PACKAGE_ROOT", tmp_path)
    monkeypatch.setattr(f"{_AC_PATH}._CODE_FINGERPRINT_SOURCES", ("names.py",))
    _code_fingerprint.cache_clear()
    try:
        first = _code_fingerprint()
        source.write_text("FOLD = 2\n", encoding="utf-8")
        _code_fingerprint.cache_clear()
        assert _code_fingerprint() != first
    finally:
        _code_fingerprint.cache_clear()


@pytest.mark.skipif(os.name == "nt", reason="NTFS names are UTF-16; undecodable byte names are POSIX-only")
def test_cache_key_keeps_non_utf8_names_distinct(tmp_path: Path) -> None:
    """A lossy UTF-8 encode would collide two undecodable file names."""
    first = tmp_path / os.fsdecode(b"Bad\xffName.s")
    second = tmp_path / os.fsdecode(b"Bad\xfeName.s")
    cache = FileASTCache(tmp_path)

    assert cache._key(first, "draft") != cache._key(second, "draft")


def test_load_does_not_create_the_hmac_key(tmp_path: Path) -> None:
    """Only a writer creates the key; a reader with no key has a miss."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    _key_path(cache).unlink()

    assert cache.load(code_path, "draft") is None
    assert not _key_path(cache).exists()


def test_prune_drops_an_entry_whose_source_is_gone(tmp_path: Path) -> None:
    """A renamed or deleted tree must not leave unreachable entries behind."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    assert cache.load(code_path, "draft") is not None

    code_path.unlink()

    assert cache.prune_stale_entries() == 1
    assert list(cache.cache_dir.glob("*.pickle")) == []


def test_prune_caps_the_entry_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = FileASTCache(tmp_path)
    first = _write_code(tmp_path, "A.s")
    second = _write_code(tmp_path, "B.s")
    cache.save(first, "draft", _picture(first))
    cache.save(second, "draft", _picture(second))
    monkeypatch.setattr(f"{_AC_PATH}.MAX_AST_CACHE_ENTRIES", 1)

    assert cache.prune_stale_entries() == 1

    assert len(list(cache.cache_dir.glob("*.pickle"))) == 1
    survivors = [cache.load(path, "draft") is not None for path in (first, second)]
    assert survivors.count(True) == 1


def test_startup_prune_enforces_the_cap_when_identity_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A long-lived cache stays bounded even when nothing else changed."""
    cache = FileASTCache(tmp_path)
    for name in ("A.s", "B.s"):
        code_path = _write_code(tmp_path, name)
        cache.save(code_path, "draft", _picture(code_path))
    monkeypatch.setattr(f"{_AC_PATH}.MAX_AST_CACHE_ENTRIES", 1)

    restarted = FileASTCache(tmp_path)

    assert restarted.drain_startup_pruned_entries() == 1
    assert len(list(restarted.cache_dir.glob("*.pickle"))) == 1


def test_stored_source_exists_rejects_a_missing_or_malformed_path() -> None:
    assert _stored_source_exists({}) is False
    assert _stored_source_exists({"path": ""}) is False
    assert _stored_source_exists({"path": 1}) is False


def test_entry_cap_is_a_noop_without_a_cache_directory(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    shutil.rmtree(cache.cache_dir)

    assert cache._enforce_entry_cap() == 0


def test_entry_cap_skips_a_pickle_whose_stat_disappears(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = FileASTCache(tmp_path)
    (cache.cache_dir / "gone.pickle").write_bytes(b"x")

    def _no_stat(_path: Path) -> object:
        return None

    monkeypatch.setattr(f"{_AC_PATH}._safe_stat", _no_stat)

    assert cache._enforce_entry_cap() == 0
