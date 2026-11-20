# pyright: reportPrivateUsage=false
"""Policy tests for the private-cache-directory security checks.

The access decision is pure, so the whole Windows ACL policy is exercised on
every platform with synthetic ACEs. The integration tests that touch a real
security descriptor are Windows-only and are skipped elsewhere; Linux CI relies
on the policy tests plus the Windows job.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from sattline_parser._cache_security import (
    AccessControlEntry,
    _windows_privacy_report,
    acl_is_private,
    is_reparse_point,
    windows_directory_is_private,
)

_USER = "S-1-5-21-1111111111-2222222222-3333333333-1001"
_OTHER_USER = "S-1-5-21-1111111111-2222222222-3333333333-1002"
_EVERYONE = "S-1-1-0"
_AUTHENTICATED_USERS = "S-1-5-11"
_USERS = "S-1-5-32-545"
_ANONYMOUS = "S-1-5-7"
_SYSTEM = "S-1-5-18"
_ADMINISTRATORS = "S-1-5-32-544"
_OWNER_RIGHTS = "S-1-3-4"

_FULL_CONTROL = 0x001F01FF
_WRITE_DATA = 0x00000002
_DELETE = 0x00010000
_WRITE_DAC = 0x00040000
_WRITE_OWNER = 0x00080000
_GENERIC_ALL = 0x10000000
_READ_ONLY = 0x00000001

_INHERIT_ONLY = 0x08
_ALLOWED = 0
_DENIED = 1
_OBJECT_ALLOWED = 5


def _ace(sid: str, mask: int, *, flags: int = 0, ace_type: int = _ALLOWED) -> AccessControlEntry:
    return AccessControlEntry(sid=sid, mask=mask, flags=flags, ace_type=ace_type)


def test_a_private_acl_needs_the_owner_to_be_this_user() -> None:
    entries = [_ace(_USER, _FULL_CONTROL)]

    assert acl_is_private(_USER, entries, _USER)
    assert not acl_is_private(_OTHER_USER, entries, _USER)
    assert not acl_is_private(_ADMINISTRATORS, entries, _USER)
    assert not acl_is_private(None, entries, _USER)
    assert not acl_is_private(_USER, entries, None)


def test_a_null_dacl_is_never_private() -> None:
    """A directory with no DACL grants every trustee full access."""
    assert not acl_is_private(_USER, None, _USER)


def test_an_empty_dacl_is_private() -> None:
    assert acl_is_private(_USER, [], _USER)


@pytest.mark.parametrize(
    "sid",
    [_EVERYONE, _AUTHENTICATED_USERS, _USERS, _ANONYMOUS, _OTHER_USER],
)
@pytest.mark.parametrize(
    "mask",
    [_WRITE_DATA, _DELETE, _WRITE_DAC, _WRITE_OWNER, _GENERIC_ALL, _FULL_CONTROL],
)
def test_a_foreign_write_ace_is_rejected(sid: str, mask: int) -> None:
    assert not acl_is_private(_USER, [_ace(sid, mask)], _USER)


@pytest.mark.parametrize("sid", [_USER, _SYSTEM, _ADMINISTRATORS, _OWNER_RIGHTS])
def test_a_write_ace_for_an_accepted_trustee_is_allowed(sid: str) -> None:
    assert acl_is_private(_USER, [_ace(sid, _FULL_CONTROL)], _USER)


def test_a_read_only_foreign_ace_is_allowed() -> None:
    assert acl_is_private(_USER, [_ace(_EVERYONE, _READ_ONLY)], _USER)


def test_an_inherit_only_foreign_write_ace_does_not_apply_here() -> None:
    """The ACE applies to children, so it does not widen this directory."""
    assert acl_is_private(_USER, [_ace(_EVERYONE, _FULL_CONTROL, flags=_INHERIT_ONLY)], _USER)


def test_an_inherited_foreign_write_ace_still_counts() -> None:
    """An inherited ACE is effective on this directory, unlike an inherit-only one."""
    assert not acl_is_private(_USER, [_ace(_USERS, _FULL_CONTROL, flags=0x10)], _USER)


def test_a_deny_ace_never_grants_access() -> None:
    assert acl_is_private(_USER, [_ace(_EVERYONE, _FULL_CONTROL, ace_type=_DENIED)], _USER)


def test_an_unmodelled_ace_type_fails_closed() -> None:
    """An object ACE has a shape the policy cannot interpret."""
    assert not acl_is_private(_USER, [_ace("", _FULL_CONTROL, ace_type=_OBJECT_ALLOWED)], _USER)


def _directory_link(tmp_path: Path) -> Path:
    """A symlink to a real directory, or a skip when the platform refuses."""
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create a directory symlink")
    return link


def test_a_symlink_is_a_reparse_point(tmp_path: Path) -> None:
    assert is_reparse_point(_directory_link(tmp_path).lstat())


def test_a_windows_reparse_attribute_is_a_reparse_point() -> None:
    info = cast(os.stat_result, SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400))

    assert is_reparse_point(info)


def test_a_plain_directory_is_not_a_reparse_point(tmp_path: Path) -> None:
    assert not is_reparse_point(tmp_path.lstat())


@pytest.mark.skipif(os.name == "nt", reason="POSIX has no Windows security descriptor")
def test_the_windows_check_fails_closed_without_a_security_descriptor(tmp_path: Path) -> None:
    assert windows_directory_is_private(tmp_path) is False


def test_the_windows_check_rejects_a_reparse_point(tmp_path: Path) -> None:
    assert windows_directory_is_private(_directory_link(tmp_path)) is False


def test_the_windows_check_rejects_a_path_it_cannot_stat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_lstat(self: Path) -> os.stat_result:
        raise OSError("boom")

    monkeypatch.setattr(Path, "lstat", failing_lstat)

    assert windows_directory_is_private(tmp_path) is False


def test_the_windows_check_rejects_a_file(tmp_path: Path) -> None:
    target = tmp_path / "not-a-directory"
    target.write_text("x", encoding="utf-8")

    assert windows_directory_is_private(target) is False


@pytest.mark.skipif(os.name != "nt", reason="needs a Windows security descriptor")
def test_a_fresh_directory_is_private_on_windows(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    directory.mkdir()

    assert windows_directory_is_private(directory) is True, _windows_privacy_report(directory)


@pytest.mark.skipif(os.name != "nt", reason="needs a Windows token")
def test_windows_pytest_uses_a_private_default_owner() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "windows_pytest.py"),
            f"{__file__}::test_a_fresh_directory_is_private_on_windows",
            "-q",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != "nt", reason="needs a Windows security descriptor")
def test_a_directory_open_to_everyone_is_not_private_on_windows(tmp_path: Path) -> None:
    """The integration check: a loosened DACL must disable the cache."""
    icacls = shutil.which("icacls")
    if icacls is None:
        pytest.skip("icacls is not available")
    directory = tmp_path / "cache"
    directory.mkdir()
    grant = subprocess.run(
        [icacls, str(directory), "/grant", "*S-1-1-0:(OI)(CI)M"],
        capture_output=True,
        check=False,
    )
    if grant.returncode != 0:
        pytest.skip(f"icacls could not change the DACL: {grant.stderr.decode(errors='replace')}")

    assert windows_directory_is_private(directory) is False
