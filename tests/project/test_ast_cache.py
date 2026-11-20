# pyright: reportPrivateUsage=false
"""Unit tests for the parser-owned per-file AST cache (``project/ast_cache.py``)."""

from __future__ import annotations

import hashlib
import hmac
import os
import pickle
import shutil
import stat
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.__version__ import __version__
from sattline_parser.api import parse_source_file
from sattline_parser.grammar.resolved import grammar_fingerprint
from sattline_parser.models.ast_model import (
    BasePicture,
)
from sattline_parser.project import FILE_AST_CACHE_VERSION, FileASTCache
from sattline_parser.project._atomic import PrivateDirectory, temp_path_for
from sattline_parser.project.ast_cache import (
    _PICKLE_CACHE_MAGIC,
    _PICKLE_HMAC_KEY_NAME,
    SourceSnapshot,
    _as_data_dict,
    _code_fingerprint,
    _code_path_key,
    _create_key_exclusively,
    _decode_entry,
    _decode_header,
    _encode_entry,
    _identity_digest,
    _install_key,
    _load_or_create_key,
    _matches_source_identity,
    _read_entry,
    _runtime_identity,
    _safe_stat,
    _split_entry,
    _split_head,
    _temp_file_is_abandoned,
    _write_entry,
    source_snapshot,
)

_AC_PATH = "sattline_parser.project.ast_cache"


def _handle(directory: Path) -> PrivateDirectory | None:
    """A private-directory handle the path-based helpers below operate through."""
    return PrivateDirectory.open(directory, create=True)


def _read_signed_pickle_envelope(raw: bytes) -> tuple[str | None, bytes]:
    head = _split_head(raw)
    if head is None:
        return None, b""
    header_signature, _, header = head
    try:
        return header_signature.decode("ascii"), header
    except UnicodeDecodeError:
        return None, b""


def _read_pickle_hmac_key(key_path: Path) -> bytes | None:
    handle = _handle(key_path.parent)
    if handle is None:
        return None
    try:
        key = handle.read(key_path.name)
    finally:
        handle.close()
    if key is None or len(key) != 32:
        return None
    return key


def _load_or_create_pickle_hmac_key(directory: Path) -> bytes | None:
    handle = _handle(directory)
    if handle is None:
        return None
    try:
        return _load_or_create_key(handle)
    finally:
        handle.close()


def _create_pickle_hmac_key_exclusively(key_path: Path, key: bytes) -> bytes | None:
    handle = _handle(key_path.parent)
    if handle is None:
        return None
    try:
        return _create_key_exclusively(handle, key)
    finally:
        handle.close()


def _load_pickle_payload(path: Path) -> object | None:
    handle = _handle(path.parent)
    if handle is None:
        return None
    try:
        return _read_entry(handle, path.name)
    finally:
        handle.close()


def _save_pickle_payload(path: Path, payload: object) -> None:
    handle = _handle(path.parent)
    if handle is None:
        raise OSError(f"Could not open a private cache directory for {path.parent}")
    try:
        _write_entry(handle, path.name, payload)
    finally:
        handle.close()


def _remove_file(path: Path) -> bool:
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _temp_path_for(path: Path) -> Path:
    return temp_path_for(path)


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
    # Write bytes so Windows does not translate the fixture's LF endings into
    # CRLF, which would make a same-length edit look like a size change.
    path.write_bytes(_MINIMAL_SOURCE.encode("utf-8"))
    return path


def _picture(code_path: Path) -> BasePicture:
    return parse_source_file(code_path)


def _key_path(cache: FileASTCache) -> Path:
    return cache.cache_dir / _PICKLE_HMAC_KEY_NAME


def _envelope(
    *,
    header_signature: bytes = b"0" * 64,
    payload_signature: bytes = b"0" * 64,
    length: bytes = b"00000000",
    header: bytes = b"",
    payload: bytes = b"",
) -> bytes:
    return _PICKLE_CACHE_MAGIC + header_signature + b"\n" + payload_signature + b"\n" + length + header + payload


def test_envelope_rejects_wrong_magic() -> None:
    assert _read_signed_pickle_envelope(b"nope") == (None, b"")


def test_envelope_rejects_a_missing_header_separator() -> None:
    assert _read_signed_pickle_envelope(_PICKLE_CACHE_MAGIC + b"a" * 64 + b"X") == (None, b"")


def test_envelope_rejects_a_missing_payload_signature_separator() -> None:
    envelope = _PICKLE_CACHE_MAGIC + b"a" * 64 + b"\n" + b"b" * 64 + b"X"
    assert _read_signed_pickle_envelope(envelope) == (None, b"")


def test_envelope_rejects_wrong_signature_lengths() -> None:
    assert _read_signed_pickle_envelope(_envelope(header_signature=b"a" * 63)) == (None, b"")
    assert _read_signed_pickle_envelope(_envelope(payload_signature=b"a" * 65)) == (None, b"")


def test_envelope_rejects_a_non_numeric_header_length() -> None:
    assert _read_signed_pickle_envelope(_envelope(length=b"abcdefgh")) == (None, b"")


def test_envelope_rejects_too_long_a_header_length() -> None:
    assert _read_signed_pickle_envelope(_envelope(length=b"99999999")) == (None, b"")


def test_envelope_rejects_a_truncated_header() -> None:
    assert _read_signed_pickle_envelope(_envelope(length=b"00000010", header=b"{}")) == (None, b"")


def test_envelope_rejects_non_ascii_signature() -> None:
    assert _read_signed_pickle_envelope(_envelope(header_signature=b"\xff" * 64)) == (None, b"")


def test_envelope_round_trip() -> None:
    """The header split reports the signature and header of a complete envelope."""
    data = _encode_entry({"version": 1, "meta": {"path": "/x"}}, b"k" * 32)

    signature, header = _read_signed_pickle_envelope(data)

    assert signature is not None
    assert header == b'{"path":"/x"}'


def test_split_entry_rejects_a_malformed_envelope() -> None:
    assert _split_entry(b"junk") is None


def test_decode_entry_rejects_a_malformed_envelope() -> None:
    assert _decode_entry(b"junk", b"k" * 32) is None


def test_decode_header_rejects_a_malformed_envelope() -> None:
    assert _decode_header(b"junk", b"k" * 32) is None


def test_decode_header_rejects_a_foreign_signature() -> None:
    assert _decode_header(_envelope(), b"k" * 32) is None


def _signed_header(header: bytes, key: bytes) -> bytes:
    signature = hmac.new(key, header, hashlib.sha256).hexdigest().encode("ascii")
    return _envelope(header_signature=signature, length=f"{len(header):08d}".encode("ascii"), header=header)


def test_decode_header_rejects_invalid_json() -> None:
    key = b"k" * 32
    assert _decode_header(_signed_header(b"notjson", key), key) is None


def test_decode_header_rejects_json_that_is_not_a_mapping() -> None:
    key = b"k" * 32
    assert _decode_header(_signed_header(b"[]", key), key) is None


def test_decode_header_accepts_a_signed_mapping() -> None:
    key = b"k" * 32
    assert _decode_header(_signed_header(b'{"path":"/x"}', key), key) == {"path": "/x"}


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


def test_load_or_create_hmac_key_leaves_an_invalid_existing_key_alone(tmp_path: Path) -> None:
    key_path = tmp_path / _PICKLE_HMAC_KEY_NAME
    key_path.write_bytes(b"toolong")
    assert _load_or_create_pickle_hmac_key(tmp_path) is None
    assert key_path.read_bytes() == b"toolong"


def test_load_or_create_hmac_key_race_returns_concurrent_key(tmp_path: Path) -> None:
    """The loser of the link race reads the winner's key instead of deleting it."""

    def _race(source: object, target: object, **_: object) -> None:
        (tmp_path / str(target)).write_bytes(b"y" * 32)
        raise FileExistsError

    with patch(f"{_AC_PATH}.os.link", side_effect=_race):
        result = _load_or_create_pickle_hmac_key(tmp_path)
    assert result == b"y" * 32
    assert (tmp_path / _PICKLE_HMAC_KEY_NAME).read_bytes() == b"y" * 32


def test_load_or_create_hmac_key_publishes_complete_bytes(tmp_path: Path) -> None:
    """The key appears under its final name only after it is fully written."""
    seen: list[bytes] = []
    real_link = os.link

    def _link(source: object, target: object, **kwargs: object) -> None:
        seen.append((tmp_path / str(source)).read_bytes())
        real_link(source, target, **kwargs)  # type: ignore[arg-type]

    with patch(f"{_AC_PATH}.os.link", side_effect=_link):
        key = _load_or_create_pickle_hmac_key(tmp_path)

    assert key is not None and len(key) == 32
    assert seen == [key]
    assert not list(tmp_path.glob("*.tmp"))


def test_load_or_create_hmac_key_falls_back_without_hard_links(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.os.link", side_effect=OSError("no hard links here")):
        key = _load_or_create_pickle_hmac_key(tmp_path)

    assert key is not None
    assert _read_pickle_hmac_key(tmp_path / _PICKLE_HMAC_KEY_NAME) == key


def test_the_exclusive_fallback_returns_a_concurrent_key(tmp_path: Path) -> None:
    key_path = tmp_path / _PICKLE_HMAC_KEY_NAME
    key_path.write_bytes(b"z" * 32)

    assert _create_pickle_hmac_key_exclusively(key_path, b"k" * 32) == b"z" * 32
    assert key_path.read_bytes() == b"z" * 32


def test_the_exclusive_fallback_gives_up_when_the_open_fails(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.os.open", side_effect=OSError("boom")):
        assert _create_pickle_hmac_key_exclusively(tmp_path / _PICKLE_HMAC_KEY_NAME, b"k" * 32) is None


def test_the_exclusive_fallback_removes_only_its_own_partial_key(tmp_path: Path) -> None:
    key_path = tmp_path / _PICKLE_HMAC_KEY_NAME

    with patch(f"{_AC_PATH}.os.fsync", side_effect=OSError("boom")):
        assert _create_pickle_hmac_key_exclusively(key_path, b"k" * 32) is None

    assert not key_path.exists()


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
    key = _load_or_create_pickle_hmac_key(tmp_path)
    assert key is not None
    envelope = bytearray(_encode_entry({"version": 1}, key))
    envelope[len(_PICKLE_CACHE_MAGIC)] ^= 0x01
    target = tmp_path / "e.pickle"
    target.write_bytes(bytes(envelope))
    assert _load_pickle_payload(target) is None


def test_load_pickle_payload_rejects_a_foreign_envelope(tmp_path: Path) -> None:
    target = tmp_path / "e.pickle"
    target.write_bytes(b"no cache magic here")
    assert _load_pickle_payload(target) is None


def test_load_pickle_payload_no_key(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.os.open", side_effect=OSError("boom")):
        _load_or_create_pickle_hmac_key(tmp_path)
        target = tmp_path / "e.pickle"
        target.write_bytes(_PICKLE_CACHE_MAGIC + b"a" * 64 + b"\n" + b"00000002" + b"{}")
        assert _load_pickle_payload(target) is None


def test_load_pickle_payload_rejects_a_payload_not_covered_by_its_signature(tmp_path: Path) -> None:
    """The payload signature covers the header too, so a swapped body is a miss."""
    key = _load_or_create_pickle_hmac_key(tmp_path)
    assert key is not None
    good = _encode_entry({"version": 1}, key)
    entry = _decode_entry(good, key)
    assert entry is not None
    other = pickle.dumps({"version": 2}, protocol=pickle.HIGHEST_PROTOCOL)
    target = tmp_path / "e.pickle"
    target.write_bytes(good[: len(good) - len(entry.payload)] + other)
    assert _load_pickle_payload(target) is None


def test_load_pickle_payload_rejects_an_unpickle_error(tmp_path: Path) -> None:
    key = _load_or_create_pickle_hmac_key(tmp_path)
    assert key is not None
    target = tmp_path / "e.pickle"
    target.write_bytes(_encode_entry({"version": 1}, key))
    with patch(f"{_AC_PATH}.pickle.loads", side_effect=KeyError("boom")):
        assert _load_pickle_payload(target) is None


def test_save_pickle_payload_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "e.pickle"
    _save_pickle_payload(target, {"version": 1, "value": "ok"})
    assert _load_pickle_payload(target) == {"version": 1, "value": "ok"}


@pytest.mark.skipif(os.name != "posix", reason="Windows has no POSIX permission bits")
def test_save_pickle_payload_creates_a_private_entry_file(tmp_path: Path) -> None:
    target = tmp_path / "e.pickle"

    _save_pickle_payload(target, {"version": 1})

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_save_after_directory_deletion_refuses_to_recreate_it(tmp_path: Path) -> None:
    """A removed cache root is refused, never recreated for the rest of the run.

    Recreating the tree would write into whatever now owns the path, which is
    exactly the swap this cache refuses. The next process opens a fresh cache.
    """
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    ast = _picture(code_path)
    cache.save(code_path, "draft", ast)
    shutil.rmtree(cache.cache_dir)

    cache.save(code_path, "draft", ast)

    assert not cache.enabled
    assert not cache.cache_dir.exists()
    assert cache.load(code_path, "draft") is None


def test_save_pickle_payload_replace_failure(tmp_path: Path) -> None:
    target = tmp_path / "e.pickle"
    with patch(f"{_AC_PATH}.os.replace", side_effect=OSError("boom")), pytest.raises(OSError, match="boom"):
        _save_pickle_payload(target, {"version": 1})
    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_constructor_disables_the_cache_when_the_fingerprint_is_unreadable(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}._code_fingerprint", side_effect=OSError("boom")):
        cache = FileASTCache(tmp_path)

    assert not cache.enabled


def test_constructor_disables_the_cache_when_the_startup_prune_fails(tmp_path: Path) -> None:
    with patch(f"{_AC_PATH}.FileASTCache._initial_prune", side_effect=OSError("boom")):
        cache = FileASTCache(tmp_path)

    assert not cache.enabled


def test_load_or_create_hmac_key_rejects_a_non_private_directory(tmp_path: Path) -> None:
    with patch("sattline_parser.project._atomic.private_cache_dir", return_value=None):
        assert _load_or_create_pickle_hmac_key(tmp_path) is None


def test_save_is_a_noop_when_pickling_fails(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)

    with patch(f"{_AC_PATH}.pickle.dumps", side_effect=TypeError("boom")):
        cache.save(code_path, "draft", _picture(code_path))

    assert list(cache.cache_dir.glob("*.pickle")) == []


def test_load_returns_none_when_unpickling_raises_an_unexpected_error(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))

    with patch(f"{_AC_PATH}.pickle.loads", side_effect=KeyError("boom")):
        assert cache.load(code_path, "draft") is None


def test_temp_paths_are_unique_per_write(tmp_path: Path) -> None:
    """Two writers must never share a temporary path."""
    target = tmp_path / "e.pickle"

    assert _temp_path_for(target) != _temp_path_for(target)


def test_save_pickle_payload_key_failure(tmp_path: Path) -> None:
    handle = PrivateDirectory.open(tmp_path, create=True)
    assert handle is not None
    try:
        with (
            patch(f"{_AC_PATH}._load_or_create_key", return_value=None),
            pytest.raises(OSError, match="pickle HMAC key"),
        ):
            _write_entry(handle, "e.pickle", {"version": 1})
    finally:
        handle.close()


def test_load_missing_entry_returns_none(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    assert cache.enabled
    assert cache.load(code_path, "draft") is None


def test_cache_is_disabled_when_the_root_is_not_owned_by_this_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code_path = _write_code(tmp_path)
    monkeypatch.setattr("sattline_parser.source_io._IS_WINDOWS", False)
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
    monkeypatch.setattr("sattline_parser.source_io._IS_WINDOWS", False)
    monkeypatch.setattr("sattline_parser.source_io._getuid", lambda: -1)
    (tmp_path / "cache").mkdir()

    cache = FileASTCache(tmp_path / "cache")

    assert not cache.enabled
    assert not cache.cache_dir.exists()
    assert cache.load(code_path, "draft") is None


def test_cache_is_disabled_when_the_windows_check_rejects_the_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Windows branch must disable the cache, not fall back to a mode check."""
    code_path = _write_code(tmp_path)

    def not_private(path: Path) -> bool:
        del path
        return False

    monkeypatch.setattr("sattline_parser.source_io._IS_WINDOWS", True)
    monkeypatch.setattr("sattline_parser.source_io.windows_directory_is_private", not_private)

    cache = FileASTCache(tmp_path / "cache")

    assert not cache.enabled
    cache.save(code_path, "draft", _picture(code_path))
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

    with patch(f"{_AC_PATH}._read_entry", side_effect=AssertionError("must not unpickle at startup")):
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
                "runtime": _runtime_identity(),
                "code": cache._fingerprint,
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
    with patch.object(cache, "_fingerprint", "0" * 64):
        assert cache._key(code_path, "draft") != key


@pytest.mark.parametrize(
    ("target", "value"),
    [
        (f"{_AC_PATH}.lark_version", "0.0.1"),
        (f"{_AC_PATH}._REGEX_VERSION", "0.0.1"),
        (f"{_AC_PATH}._interpreter_version", lambda: "0.0.1"),
    ],
)
def test_a_parser_stack_change_changes_the_identity_and_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, value: object
) -> None:
    """A dependency or interpreter upgrade must reach both the identity and the key."""
    cache = FileASTCache(tmp_path)
    code_path = _write_code(tmp_path)
    identity = cache._identity_text()
    key = cache._key(code_path, "draft")

    monkeypatch.setattr(target, value)

    assert cache._identity_text() != identity
    assert cache._key(code_path, "draft") != key


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("parser_version", "0.0.0"),
        ("grammar", "0" * 64),
        ("runtime", "lark=0"),
        ("code", "0" * 64),
    ],
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
        "runtime": _runtime_identity(),
        "code": cache._fingerprint,
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
                "runtime": _runtime_identity(),
                "code": cache._fingerprint,
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
    assert restored.moduledef is not None
    polygon = next(obj for obj in restored.moduledef.graph_objects if obj.type == "PolygonObject")
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


def test_code_fingerprint_covers_python_and_data_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lexer fix and a scanner-token change must both invalidate an AST."""
    package = tmp_path / "package"
    (package / "grammar").mkdir(parents=True)
    (package / "preprocessing").mkdir()
    (package / "grammar" / "sattline_lexer.py").write_text("TOKEN = 1\n", encoding="utf-8")
    tokens = package / "preprocessing" / "scanner_tokens.json"
    tokens.write_text('{"#01": "A"}\n', encoding="utf-8")
    monkeypatch.setattr(f"{_AC_PATH}._PACKAGE_ROOT", package)
    _code_fingerprint.cache_clear()
    try:
        first = _code_fingerprint()
        tokens.write_text('{"#01": "B"}\n', encoding="utf-8")
        _code_fingerprint.cache_clear()
        assert _code_fingerprint() != first
    finally:
        _code_fingerprint.cache_clear()


def test_code_fingerprint_hashes_a_standalone_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "names.py"
    source.write_text("FOLD = 1\n", encoding="utf-8")
    monkeypatch.setattr(f"{_AC_PATH}._PACKAGE_ROOT", tmp_path)
    _code_fingerprint.cache_clear()
    try:
        first = _code_fingerprint()
        source.write_text("FOLD = 2\n", encoding="utf-8")
        _code_fingerprint.cache_clear()
        assert _code_fingerprint() != first
    finally:
        _code_fingerprint.cache_clear()


def test_code_fingerprint_changes_when_a_new_resource_appears(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "package"
    package.mkdir()
    monkeypatch.setattr(f"{_AC_PATH}._PACKAGE_ROOT", package)
    _code_fingerprint.cache_clear()
    try:
        first = _code_fingerprint()
        (package / "new_resource.json").write_text("{}\n", encoding="utf-8")
        _code_fingerprint.cache_clear()
        assert _code_fingerprint() != first
    finally:
        _code_fingerprint.cache_clear()


def test_code_fingerprint_ignores_bytecode_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(f"{_AC_PATH}._PACKAGE_ROOT", package)
    _code_fingerprint.cache_clear()
    try:
        first = _code_fingerprint()
        cache = package / "__pycache__"
        cache.mkdir()
        (cache / "module.cpython-312.pyc").write_bytes(b"generated")
        (package / "module.pyo").write_bytes(b"generated")
        _code_fingerprint.cache_clear()
        assert _code_fingerprint() == first
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


def test_a_gone_source_is_a_miss(tmp_path: Path) -> None:
    """A renamed or deleted tree leaves an entry that load rejects.

    ``load`` checks the recorded source revision, so a gone source is a miss.
    The entry itself is dropped by the next prune, which reads its signed header
    without unpickling the payload.
    """
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    assert cache.load(code_path, "draft") is not None

    code_path.unlink()

    assert cache.load(code_path, "draft") is None
    assert len(list(cache.cache_dir.glob("*.pickle"))) == 1
    assert cache.prune_stale_entries() == 1
    assert list(cache.cache_dir.glob("*.pickle")) == []


def test_prune_caps_the_entry_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = FileASTCache(tmp_path)
    first = _write_code(tmp_path, "A.s")
    second = _write_code(tmp_path, "B.s")
    cache.save(first, "draft", _picture(first))
    cache.save(second, "draft", _picture(second))
    monkeypatch.setattr(cache, "_max_entries", 1)

    assert cache.prune_stale_entries() == 1

    assert len(list(cache.cache_dir.glob("*.pickle"))) == 1
    survivors = [cache.load(path, "draft") is not None for path in (first, second)]
    assert survivors.count(True) == 1


def test_entry_cap_uses_max_entries_and_last_use(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    paths = [_write_code(tmp_path, name) for name in ("A.s", "B.s", "C.s")]
    for code_path in paths:
        cache.save(code_path, "draft", _picture(code_path))
    # Pin B and C to explicit old mtimes one second apart, so neither a coarse
    # filesystem nor the hash filename tiebreak can change the eviction order.
    # A's load moves it ahead of both. A whole-second stamp survives filesystems
    # that clamp a tiny ``ns`` value to the same instant.
    base = 1_600_000_000_000_000_000
    for index, code_path in enumerate(paths[1:], start=1):
        stamp = base + index * 1_000_000_000
        os.utime(cache._path(code_path, "draft"), ns=(stamp, stamp))

    assert cache.load(paths[0], "draft") is not None

    restarted = FileASTCache(tmp_path, max_entries=2)

    assert restarted.enabled
    assert restarted.load(paths[0], "draft") is not None
    assert restarted.load(paths[1], "draft") is None
    assert restarted.load(paths[2], "draft") is not None


def test_a_symlinked_entry_is_not_followed(tmp_path: Path, symlink_supported: None) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    entry = cache._path(code_path, "draft")
    outside = tmp_path / "outside.pickle"
    entry.replace(outside)
    entry.symlink_to(outside)

    assert cache.load(code_path, "draft") is None


def test_startup_prune_enforces_the_cap_when_identity_matches(tmp_path: Path) -> None:
    """A long-lived cache stays bounded even when nothing else changed."""
    cache = FileASTCache(tmp_path)
    for name in ("A.s", "B.s"):
        code_path = _write_code(tmp_path, name)
        cache.save(code_path, "draft", _picture(code_path))

    restarted = FileASTCache(tmp_path, max_entries=1)

    assert restarted.drain_startup_pruned_entries() == 1
    assert len(list(restarted.cache_dir.glob("*.pickle"))) == 1


def test_entry_cap_is_a_noop_without_a_cache_directory(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    shutil.rmtree(cache.cache_dir)

    assert cache._enforce_entry_cap() == 0


def test_entry_cap_skips_a_pickle_whose_stat_disappears(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = FileASTCache(tmp_path)
    (cache.cache_dir / "gone.pickle").write_bytes(b"x")

    def _no_stat(_self: PrivateDirectory, _name: str) -> None:
        return None

    monkeypatch.setattr(f"{_AC_PATH}.PrivateDirectory.stat", _no_stat)

    assert cache._enforce_entry_cap() == 0


def test_the_entry_key_includes_the_envelope_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A shape change must invalidate entries even before a payload is read."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    before = cache._key(code_path, "draft")

    monkeypatch.setattr(f"{_AC_PATH}.FILE_AST_CACHE_VERSION", FILE_AST_CACHE_VERSION + 1)

    assert cache._key(code_path, "draft") != before


def test_entry_names_carry_the_identity_prefix(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))

    entry = cache._path(code_path, "draft")

    assert cache._identity == _identity_digest(cache._identity_text())
    assert entry.name.startswith(f"{cache._identity}-")


def test_a_changed_identity_prunes_foreign_entry_names_only(tmp_path: Path) -> None:
    """Pruning compares the identity prefix, so it never unpickles an entry."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    entry = cache._path(code_path, "draft")
    foreign = cache.cache_dir / f"{'0' * 64}-foreign.pickle"
    foreign.write_bytes(b"x")
    (cache.cache_dir / ".parser-identity").write_text("stale identity\n", encoding="ascii")

    restarted = FileASTCache(tmp_path)

    assert restarted.drain_startup_pruned_entries() == 1
    assert entry.is_file()
    assert not foreign.exists()
    assert restarted.load(code_path, "draft") is not None


def test_a_read_only_handle_never_writes_or_touches_an_entry(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    writer = FileASTCache(tmp_path)
    writer.save(code_path, "draft", _picture(code_path))
    entry = writer._path(code_path, "draft")
    stamp = entry.stat().st_mtime_ns

    reader = FileASTCache(tmp_path, read_only=True)

    assert reader.enabled
    assert reader.read_only
    assert reader.load(code_path, "draft") is not None
    assert entry.stat().st_mtime_ns == stamp
    reader.save(code_path, "draft", _picture(code_path))
    assert entry.stat().st_mtime_ns == stamp
    assert reader.prune_stale_entries() == 0
    assert reader._prune_temporary_files() == 0
    assert reader._enforce_entry_cap() == 0
    assert reader.drain_startup_pruned_entries() == 0


def test_a_read_only_handle_leaves_maintenance_to_the_parent(tmp_path: Path) -> None:
    writer = FileASTCache(tmp_path)
    abandoned = writer.cache_dir / "leftover.pickle.tmp"
    abandoned.write_bytes(b"x")
    old = time.time() - 7200
    os.utime(abandoned, (old, old))
    foreign = writer.cache_dir / "foreign.pickle"
    foreign.write_bytes(b"x")
    marker = writer.cache_dir / ".parser-identity"
    marker_bytes = marker.read_bytes()

    reader = FileASTCache(tmp_path, read_only=True)

    assert reader.enabled
    assert abandoned.exists()
    assert foreign.exists()
    assert marker.read_bytes() == marker_bytes


def test_a_read_only_handle_does_not_create_the_cache_directory(tmp_path: Path) -> None:
    reader = FileASTCache(tmp_path / "cache", read_only=True)

    assert not reader.enabled
    assert not (tmp_path / "cache").exists()


def test_a_read_only_handle_still_requires_a_private_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    (cache_dir / "file_ast").mkdir(parents=True)
    monkeypatch.setattr("sattline_parser.source_io._IS_WINDOWS", False)
    monkeypatch.setattr("sattline_parser.source_io._getuid", lambda: -1)

    assert not FileASTCache(cache_dir, read_only=True).enabled


def test_a_key_is_not_created_for_a_refused_handle(tmp_path: Path) -> None:
    handle = PrivateDirectory.open(tmp_path, create=True)
    assert handle is not None
    handle.close()

    assert _load_or_create_key(handle) is None


def test_the_key_install_gives_up_when_the_temporary_name_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = PrivateDirectory.open(tmp_path, create=True)
    assert handle is not None
    try:

        def _taken(_name: str, _data: bytes) -> bool:
            raise FileExistsError

        monkeypatch.setattr(handle, "create_exclusive", _taken)
        assert _install_key(handle, b"k" * 32) is None
    finally:
        handle.close()


def test_prune_skips_a_temporary_name_that_is_not_a_file(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    (cache.cache_dir / "leftover.pickle.tmp").mkdir()

    assert cache._prune_temporary_files() == 0
    assert (cache.cache_dir / "leftover.pickle.tmp").is_dir()


def test_prune_vanished_sources_is_a_noop_for_a_read_only_handle(tmp_path: Path) -> None:
    FileASTCache(tmp_path)
    reader = FileASTCache(tmp_path, read_only=True)

    assert reader._prune_vanished_sources() == 0


def test_prune_vanished_sources_is_a_noop_for_a_disabled_handle(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    (cache_root / "file_ast").write_bytes(b"not a directory")
    cache = FileASTCache(cache_root)

    assert not cache.enabled
    assert cache._prune_vanished_sources() == 0
