# pyright: reportPrivateUsage=false
"""Unit tests for the parser-owned per-file AST cache (``project/ast_cache.py``)."""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.api import parse_source_file
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.project import FILE_AST_CACHE_VERSION, FileASTCache
from sattline_parser.project.ast_cache import (
    _PICKLE_CACHE_MAGIC,
    _PICKLE_HMAC_KEY_NAME,
    _as_data_dict,
    _code_path_key,
    _load_or_create_pickle_hmac_key,
    _load_pickle_payload,
    _matches_stat_snapshot,
    _read_pickle_hmac_key,
    _read_signed_pickle_envelope,
    _remove_file,
    _safe_stat,
    _save_pickle_payload,
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


def test_matches_stat_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_text("abc", encoding="utf-8")
    stat_result = path.stat()
    assert _matches_stat_snapshot(path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size)
    assert not _matches_stat_snapshot(path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size + 1)
    path.unlink()
    assert not _matches_stat_snapshot(path, mtime_ns=stat_result.st_mtime_ns, size=stat_result.st_size)
    assert not _matches_stat_snapshot(path, mtime_ns="x", size=stat_result.st_size)


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
    assert not (tmp_path / "e.pickle.tmp").exists()


def test_save_pickle_payload_key_failure(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.os.open", side_effect=OSError("boom")), pytest.raises(OSError, match="pickle HMAC key"):
        _save_pickle_payload(tmp_path / "e.pickle", {"version": 1})


def test_load_missing_entry_returns_none(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    assert cache.load(code_path, "draft") is None


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
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
            },
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
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
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
            },
        ),
        "bad-mode": _payload(
            "bad-mode",
            meta={
                "path": str(code_path),
                "mode": "WRONG",
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
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
    foreign = cache.cache_dir / "foreign.pickle"
    foreign.write_bytes(b"no magic")
    tmp = cache.cache_dir / "leftover.pickle.tmp"
    tmp.write_bytes(b"x")
    subdir = cache.cache_dir / "subdir"
    subdir.mkdir()

    removed = cache.prune_stale_entries()

    assert removed == 3
    assert cache.load(code_path, "draft") is not None
    assert not stale.exists()
    assert not foreign.exists()
    assert not tmp.exists()
    assert subdir.is_dir()


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
