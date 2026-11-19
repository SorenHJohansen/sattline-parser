# pyright: reportPrivateUsage=false
"""Unit tests for :class:`sattline_parser.project._atomic.PrivateDirectory`.

The POSIX form holds a directory descriptor; the Windows form performs the same
operations by path because Windows cannot open a directory portably. Both forms
are exercised on Linux by forcing the path form, so the Windows half of the
boundary is tested on every platform instead of only in the Windows job.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.project import _atomic
from sattline_parser.project._atomic import (
    MAX_ENTRY_BYTES,
    PrivateDirectory,
    _fstat,
    _lstat,
    _read_all,
    _read_prefix,
    _write_all,
    temp_file_is_abandoned,
    temp_name_for,
    temp_path_for,
)


@pytest.fixture
def path_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the descriptor-free form, which is what Windows uses."""
    monkeypatch.setattr(_atomic, "_USES_DIRECTORY_DESCRIPTOR", False)


def _open(directory: Path) -> PrivateDirectory:
    handle = PrivateDirectory.open(directory, create=True)
    assert handle is not None
    return handle


def _descriptor_for(path: Path) -> int:
    return os.open(path, os.O_RDONLY)


def test_temp_names_are_unique_and_share_a_suffix() -> None:
    first = temp_name_for("entry.pickle")
    second = temp_name_for("entry.pickle")

    assert first != second
    assert first.startswith("entry.pickle.")
    assert first.endswith(".tmp")
    path = temp_path_for(Path("/x/entry.pickle"))
    assert path.parent == Path("/x")
    assert path.name.startswith("entry.pickle.")


def test_temp_file_is_abandoned_for_a_missing_path(tmp_path: Path) -> None:
    assert temp_file_is_abandoned(tmp_path / "gone.pickle.tmp")


def test_lstat_reports_a_missing_path(tmp_path: Path) -> None:
    assert _lstat(tmp_path / "missing") is None
    assert _lstat(tmp_path) is not None


def test_read_all_rejects_a_bad_descriptor_and_a_non_regular_entry(tmp_path: Path) -> None:
    assert _read_all(-1) is None
    directory_fd = _descriptor_for(tmp_path)
    try:
        assert _read_all(directory_fd) is None
    finally:
        os.close(directory_fd)


def test_read_all_rejects_an_oversized_entry(tmp_path: Path) -> None:
    target = tmp_path / "huge"
    with target.open("wb") as handle:
        handle.truncate(MAX_ENTRY_BYTES + 1)
    descriptor = _descriptor_for(target)
    try:
        assert _read_all(descriptor) is None
    finally:
        os.close(descriptor)


def test_write_all_rejects_a_bad_descriptor() -> None:
    assert not _write_all(-1, b"x")


def test_path_mode_round_trip(path_mode: None, tmp_path: Path) -> None:
    handle = _open(tmp_path)

    handle.write_atomic("entry.pickle", b"payload")
    assert handle.read("entry.pickle") == b"payload"
    assert handle.read_prefix("entry.pickle", 3) == b"pay"
    assert handle.read_prefix("entry.pickle", 100) == b"payload"
    assert "entry.pickle" in handle.names()
    assert handle.stat("entry.pickle") is not None
    handle.touch("entry.pickle")
    assert handle.revalidate()
    assert handle.unlink("entry.pickle")
    assert handle.read("entry.pickle") is None
    assert handle.read_prefix("entry.pickle", 4) is None
    assert handle.stat("entry.pickle") is None
    assert not handle.unlink("entry.pickle")
    handle.touch("entry.pickle")
    handle.close()
    assert not handle.revalidate()
    handle.__del__()
    assert not handle.revalidate()


def test_path_mode_never_follows_a_symlink(path_mode: None, tmp_path: Path) -> None:
    handle = _open(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"secret")
    (tmp_path / "link").symlink_to(outside)

    assert handle.read("link") is None
    assert handle.read_prefix("link", 10) is None
    assert handle.stat("link") is not None
    (tmp_path / "subdir").mkdir()
    assert handle.read("subdir") is None
    assert handle.read_prefix("subdir", 10) is None


def test_path_mode_refuses_an_oversized_entry(path_mode: None, tmp_path: Path) -> None:
    handle = _open(tmp_path)
    target = tmp_path / "huge.pickle"
    with target.open("wb") as raw:
        raw.truncate(MAX_ENTRY_BYTES + 1)

    assert handle.read("huge.pickle") is None


def test_path_mode_read_prefix_tolerates_a_read_error(
    path_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = _open(tmp_path)
    (tmp_path / "entry").write_bytes(b"payload")

    monkeypatch.setattr(Path, "open", _raise_os_error)

    assert handle.read_prefix("entry", 3) is None


def _raise_os_error(*_args: object, **_kwargs: object) -> object:
    raise OSError("boom")


def test_path_mode_write_failure_cleans_the_temporary_file(path_mode: None, tmp_path: Path) -> None:
    handle = _open(tmp_path)

    with patch(f"{_atomic.__name__}.os.fsync", side_effect=OSError("boom")), pytest.raises(OSError):
        handle.write_atomic("entry.pickle", b"payload")

    assert not (tmp_path / "entry.pickle").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_path_mode_create_exclusive_and_link(path_mode: None, tmp_path: Path) -> None:
    handle = _open(tmp_path)

    assert handle.create_exclusive("key", b"k" * 32)
    assert handle.read("key") == b"k" * 32
    with pytest.raises(FileExistsError):
        handle.create_exclusive("key", b"next")
    handle.link("key", "alias")
    assert handle.read("alias") == b"k" * 32
    with pytest.raises(FileExistsError):
        handle.link("key", "alias")


def test_path_mode_create_exclusive_tolerates_a_failed_open(
    path_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = _open(tmp_path)
    monkeypatch.setattr(handle, "_open_exclusive", _raise_os_error)

    assert not handle.create_exclusive("key", b"k" * 32)


def test_path_mode_child_and_nested_operations(path_mode: None, tmp_path: Path) -> None:
    parent = _open(tmp_path)
    child = PrivateDirectory.child(parent, "sub", create=True)

    assert child is not None
    child.write_atomic("entry", b"payload")
    assert child.read("entry") == b"payload"
    assert child.revalidate()
    child.close()
    parent.close()


def test_path_mode_revalidate_follows_the_path_policy(path_mode: None, tmp_path: Path) -> None:
    handle = _open(tmp_path)
    os.chmod(tmp_path, 0o755)
    try:
        assert not handle.revalidate()
    finally:
        os.chmod(tmp_path, 0o700)


def test_path_mode_names_and_stat_tolerate_a_removed_directory(path_mode: None, tmp_path: Path) -> None:
    handle = _open(tmp_path)
    shutil.rmtree(tmp_path)

    assert handle.names() == []
    assert handle.stat("entry") is None


def test_open_refuses_an_identity_that_changed_between_check_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory swapped between the policy check and the open is refused."""
    real_fstat = os.fstat

    def _foreign_fstat(descriptor: int) -> os.stat_result:
        info = real_fstat(descriptor)
        return os.stat_result(
            (info.st_mode, info.st_ino + 1, info.st_dev, info.st_nlink, info.st_uid, info.st_gid, 0, 0, 0, 0)
        )

    monkeypatch.setattr(_atomic, "_fstat", _foreign_fstat)

    assert PrivateDirectory.open(tmp_path, create=True) is None


def test_child_refuses_when_the_level_cannot_be_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = _open(tmp_path)

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(_atomic.os, "mkdir", _fail)

    assert PrivateDirectory.child(parent, "sub", create=True) is None
    parent.close()


def test_child_refuses_a_file_where_a_directory_belongs(tmp_path: Path) -> None:
    parent = _open(tmp_path)
    (tmp_path / "file_ast").write_bytes(b"not a directory")

    assert PrivateDirectory.child(parent, "file_ast", create=True) is None
    parent.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_child_refuses_a_foreign_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = _open(tmp_path)
    real_fstat = os.fstat

    def _foreign_fstat(descriptor: int) -> os.stat_result:
        info = real_fstat(descriptor)
        return os.stat_result(
            (info.st_mode, info.st_ino, info.st_dev, info.st_nlink, info.st_uid + 1, info.st_gid, 0, 0, 0, 0)
        )

    monkeypatch.setattr(_atomic, "_fstat", _foreign_fstat)

    assert PrivateDirectory.child(parent, "sub", create=True) is None
    parent.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_child_tightens_an_existing_wide_level(tmp_path: Path) -> None:
    parent = _open(tmp_path)
    wide = tmp_path / "wide"
    wide.mkdir()
    os.chmod(wide, 0o755)

    child = PrivateDirectory.child(parent, "wide", create=True)

    assert child is not None
    assert stat.S_IMODE(wide.stat().st_mode) == 0o700
    child.close()
    parent.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_child_refuses_when_the_wide_level_cannot_be_tightened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = _open(tmp_path)
    wide = tmp_path / "wide"
    wide.mkdir()
    os.chmod(wide, 0o755)

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(_atomic.os, "chmod", _fail)

    assert PrivateDirectory.child(parent, "wide", create=True) is None
    parent.close()


def test_revalidate_refuses_a_failed_or_non_directory_stat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = _open(tmp_path)

    def _no_stat(_descriptor: int) -> None:
        return None

    def _regular(_descriptor: int) -> os.stat_result:
        return os.stat_result((stat.S_IFREG | 0o600, 1, 1, 1, 0, 0, 0, 0, 0, 0))

    monkeypatch.setattr(_atomic, "_fstat", _no_stat)
    assert not handle.revalidate()

    monkeypatch.setattr(_atomic, "_fstat", _regular)
    assert not handle.revalidate()
    handle.close()


def test_read_helpers_reject_a_closed_descriptor(tmp_path: Path) -> None:
    target = tmp_path / "entry"
    target.write_bytes(b"payload")
    descriptor = _descriptor_for(target)
    os.close(descriptor)

    assert _read_all(descriptor) is None
    assert _read_prefix(descriptor, 3) is None


def test_read_all_reports_a_read_error(tmp_path: Path) -> None:
    """A descriptor that stats as a file but cannot be read is a miss."""
    target = tmp_path / "entry"
    target.write_bytes(b"payload")
    descriptor = os.open(target, os.O_WRONLY)

    try:
        assert _read_all(descriptor) is None
    finally:
        os.close(descriptor)


def test_fstat_reports_a_bad_descriptor() -> None:
    assert _fstat(-1) is None


def test_open_refuses_a_level_that_vanishes_after_the_policy_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_lstat(_path: Path) -> None:
        return None

    monkeypatch.setattr(_atomic, "_lstat", _no_lstat)

    assert PrivateDirectory.open(tmp_path, create=True) is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_child_refuses_a_level_that_stays_wide_after_chmod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = _open(tmp_path)
    wide = tmp_path / "wide"
    wide.mkdir()
    os.chmod(wide, 0o755)
    real_fstat = os.fstat
    calls: list[int] = []

    def _wide_fstat(descriptor: int) -> os.stat_result:
        calls.append(descriptor)
        info = real_fstat(descriptor)
        if len(calls) == 1:
            return info
        return os.stat_result(
            (info.st_mode | 0o077, info.st_ino, info.st_dev, info.st_nlink, info.st_uid, info.st_gid, 0, 0, 0, 0)
        )

    monkeypatch.setattr(_atomic, "_fstat", _wide_fstat)

    assert PrivateDirectory.child(parent, "wide", create=True) is None
    parent.close()


def test_revalidate_refuses_a_changed_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = _open(tmp_path)
    real_fstat = os.fstat

    def _moved(descriptor: int) -> os.stat_result:
        info = real_fstat(descriptor)
        return os.stat_result(
            (info.st_mode, info.st_ino + 1, info.st_dev, info.st_nlink, info.st_uid, info.st_gid, 0, 0, 0, 0)
        )

    monkeypatch.setattr(_atomic, "_fstat", _moved)

    assert not handle.revalidate()
    handle.close()


def test_path_mode_read_tolerates_a_read_error(
    path_mode: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = _open(tmp_path)
    (tmp_path / "entry").write_bytes(b"payload")

    def _fail(_self: Path) -> bytes:
        raise OSError("boom")

    monkeypatch.setattr(Path, "read_bytes", _fail)

    assert handle.read("entry") is None


def test_read_prefix_refuses_a_directory_entry(tmp_path: Path) -> None:
    handle = _open(tmp_path)
    (tmp_path / "subdir").mkdir()

    assert handle.read_prefix("subdir", 10) is None
    handle.close()


def test_a_fifo_entry_is_refused_without_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cache entry named like an artifact may be a FIFO, which never answers.

    Opening a FIFO read-only waits for a writer, so a blocking open would stop a
    load before the regular-file check ran. Both forms must answer ``None``
    immediately.
    """
    if not hasattr(os, "mkfifo"):
        pytest.skip("this platform has no FIFOs")
    os.mkfifo(tmp_path / "entry.pickle")

    handle = _open(tmp_path)
    try:
        assert handle.read("entry.pickle") is None
        assert handle.read_prefix("entry.pickle", 4) is None
    finally:
        handle.close()

    monkeypatch.setattr(_atomic, "_USES_DIRECTORY_DESCRIPTOR", False)
    path_handle = _open(tmp_path)
    try:
        assert path_handle.read("entry.pickle") is None
        assert path_handle.read_prefix("entry.pickle", 4) is None
    finally:
        path_handle.close()


def test_write_atomic_cleans_up_when_the_flush_fails(tmp_path: Path) -> None:
    handle = _open(tmp_path)

    with patch(f"{_atomic.__name__}.os.fsync", side_effect=OSError("boom")), pytest.raises(OSError):
        handle.write_atomic("entry.pickle", b"payload")

    assert not (tmp_path / "entry.pickle").exists()
    assert list(tmp_path.glob("*.tmp")) == []
    handle.close()
