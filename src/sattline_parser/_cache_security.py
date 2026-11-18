"""Platform privacy checks for the pickle-backed cache directories.

A cache directory is trusted only when the platform proves that no other user
can write it: the entries are pickles, and the HMAC key sits beside them, so a
foreign writer can replace both and plant a payload. The POSIX rule lives in
:mod:`sattline_parser.source_io`, next to the parser cache that shares it. This
module owns the Windows rule, which reads the directory's security descriptor
through :mod:`ctypes` and fails closed on anything it cannot interpret.

The access decision is a pure function (:func:`acl_is_private`) so the policy is
tested on every platform with synthetic ACEs. Only the Win32 calls that produce
that data are Windows-only.
"""

from __future__ import annotations

import ctypes
import os
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

__all__ = ["AccessControlEntry", "acl_is_private", "is_reparse_point", "windows_directory_is_private"]

#: ``ACCESS_ALLOWED_ACE_TYPE`` and ``ACCESS_DENIED_ACE_TYPE`` from ``winnt.h``.
_ACCESS_ALLOWED_ACE_TYPE = 0
_ACCESS_DENIED_ACE_TYPE = 1

#: ``INHERIT_ONLY_ACE``: the ACE applies to children, never to this directory.
_INHERIT_ONLY_ACE = 0x08

#: ``FILE_ATTRIBUTE_REPARSE_POINT``: a symlink, mount point, or other redirect.
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

#: Every access-mask bit that lets a trustee modify the directory or its DACL.
_WRITE_MASK = (
    0x00000002  # FILE_WRITE_DATA
    | 0x00000004  # FILE_APPEND_DATA
    | 0x00000010  # FILE_WRITE_EA
    | 0x00000040  # FILE_DELETE_CHILD
    | 0x00000100  # FILE_WRITE_ATTRIBUTES
    | 0x00010000  # DELETE
    | 0x00040000  # WRITE_DAC
    | 0x00080000  # WRITE_OWNER
    | 0x40000000  # GENERIC_WRITE
    | 0x10000000  # GENERIC_ALL
)

#: Trustees that may hold a write ACE on a directory this user owns.
#:
#: ``S-1-5-18`` is LOCAL SYSTEM, ``S-1-5-32-544`` is BUILTIN\\Administrators,
#: and ``S-1-3-4`` is OWNER RIGHTS. OWNER RIGHTS is accepted because the owner
#: SID was already checked against the current user, so it resolves to this
#: user; an unverified owner is rejected before any ACE is read.
_ALLOWED_WRITE_SIDS = frozenset({"S-1-5-18", "S-1-5-32-544", "S-1-3-4"})

#: Win32 constants used by the security-descriptor reader.
_SE_FILE_OBJECT = 1
_OWNER_SECURITY_INFORMATION = 0x00000001
_DACL_SECURITY_INFORMATION = 0x00000004
_TOKEN_QUERY = 0x0008
_TOKEN_USER_CLASS = 1
_ERROR_SUCCESS = 0


@dataclass(frozen=True, slots=True)
class AccessControlEntry:
    """One ACE of a Windows DACL, reduced to what the policy needs.

    ``sid`` is the canonical string form (``S-1-5-21-...``). It is empty for an
    ACE type this module does not model, which the policy rejects.
    """

    sid: str
    mask: int
    flags: int = 0
    ace_type: int = _ACCESS_ALLOWED_ACE_TYPE


def is_reparse_point(info: os.stat_result) -> bool:
    """Whether a directory entry is a symlink or another reparse point.

    ``lstat`` reports a Windows reparse point through ``st_file_attributes``;
    a POSIX symlink is visible through the mode. Either shape can redirect a
    cache write into a directory this user does not own, so both are refused.
    """
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def acl_is_private(
    owner_sid: str | None,
    entries: Sequence[AccessControlEntry] | None,
    user_sid: str | None,
) -> bool:
    """Whether an owner and DACL prove that only this user can write.

    ``entries`` is ``None`` when the directory has no DACL at all, which grants
    every trustee full access. A foreign owner is rejected before the ACEs are
    considered. Only an allowed ACE that carries a write bit can widen access,
    and it may name this user, LOCAL SYSTEM, BUILTIN\\Administrators, or OWNER
    RIGHTS. A denied ACE never grants anything, and an inherit-only ACE does not
    apply to the directory itself.
    """
    if owner_sid is None or user_sid is None or owner_sid != user_sid:
        return False
    if entries is None:
        return False
    for entry in entries:
        if entry.ace_type == _ACCESS_DENIED_ACE_TYPE:
            continue
        if entry.ace_type != _ACCESS_ALLOWED_ACE_TYPE:
            # An object or audit ACE has a shape this policy does not model.
            return False
        if entry.flags & _INHERIT_ONLY_ACE:
            continue
        if not entry.mask & _WRITE_MASK:
            continue
        if entry.sid == user_sid or entry.sid in _ALLOWED_WRITE_SIDS:
            continue
        return False
    return True


def windows_directory_is_private(path: Path) -> bool:
    """Whether *path* is a real directory this user owns privately, on Windows.

    A reparse point is rejected before the security descriptor is read, so a
    planted link cannot redirect the check. Anything the Win32 calls cannot
    establish (a missing API, a failed call, an unreadable ACE) returns
    ``False``: the cache is an optimisation, so an unproven directory disables
    it instead of being trusted.
    """
    try:
        info = path.lstat()
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode) or is_reparse_point(info):
        return False
    return _windows_security_descriptor_is_private(path)


def _windows_security_descriptor_is_private(path: Path) -> bool:  # pragma: no cover - needs Windows
    """Read the directory's owner and DACL and apply :func:`acl_is_private`."""
    if os.name != "nt":
        return False
    advapi32 = _system_dll("advapi32")
    kernel32 = _system_dll("kernel32")
    user_sid = _current_user_sid(advapi32, kernel32)
    if user_sid is None:
        return False
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = advapi32.GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != _ERROR_SUCCESS or not descriptor:
        return False
    try:
        owner_sid = _sid_to_string(advapi32, kernel32, owner)
        if owner_sid is None:
            return False
        entries = _access_control_entries(advapi32, kernel32, dacl) if dacl else None
        return acl_is_private(owner_sid, entries, user_sid)
    finally:
        kernel32.LocalFree(descriptor)


def _system_dll(name: str) -> Any:  # pragma: no cover - needs Windows
    """Load one Win32 system library with last-error reporting."""
    # ``WinDLL`` exists only in the Windows typeshed, and this module is
    # imported on every platform.
    win_dll = cast(Callable[..., Any], ctypes.WinDLL)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    return win_dll(name, use_last_error=True)


def _current_user_sid(advapi32: Any, kernel32: Any) -> str | None:  # pragma: no cover - needs Windows
    """The string SID of the user this process runs as, or ``None``."""
    token = ctypes.c_void_p()
    if advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)) == 0:
        return None
    try:
        size = ctypes.c_uint32(0)
        advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, None, 0, ctypes.byref(size))
        if not size.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, buffer, size, ctypes.byref(size)) == 0:
            return None
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
        return _sid_to_string(advapi32, kernel32, ctypes.c_void_p(token_user.user.sid))
    finally:
        kernel32.CloseHandle(token)


def _sid_to_string(advapi32: Any, kernel32: Any, sid: ctypes.c_void_p) -> str | None:  # pragma: no cover
    """Convert a binary SID to its ``S-1-...`` form, or ``None``."""
    if not sid:
        return None
    text = ctypes.c_wchar_p()
    if advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)) == 0:
        return None
    try:
        return text.value
    finally:
        kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))


def _access_control_entries(  # pragma: no cover - needs Windows
    advapi32: Any, kernel32: Any, dacl: ctypes.c_void_p
) -> tuple[AccessControlEntry, ...] | None:
    """Read every ACE of *dacl*, or ``None`` when one cannot be read."""
    acl = ctypes.cast(dacl, ctypes.POINTER(_Acl))
    entries: list[AccessControlEntry] = []
    for index in range(acl.contents.ace_count):
        ace = ctypes.c_void_p()
        if advapi32.GetAce(acl, index, ctypes.byref(ace)) == 0:
            return None
        address = ace.value
        if not address:
            return None
        header = ctypes.cast(ace, ctypes.POINTER(_Ace)).contents
        sid = ""
        if header.ace_type in (_ACCESS_ALLOWED_ACE_TYPE, _ACCESS_DENIED_ACE_TYPE):
            sid_pointer = ctypes.c_void_p(address + ctypes.sizeof(_Ace))
            sid = _sid_to_string(advapi32, kernel32, sid_pointer) or ""
            if not sid:
                return None
        entries.append(
            AccessControlEntry(
                sid=sid,
                mask=header.mask,
                flags=header.ace_flags,
                ace_type=header.ace_type,
            )
        )
    return tuple(entries)


class _Ace(ctypes.Structure):  # pragma: no cover - needs Windows
    """The fixed part of an ``ACCESS_ALLOWED_ACE`` / ``ACCESS_DENIED_ACE``.

    Every ACE starts with the four-byte ``ACE_HEADER`` and carries its access
    mask next, so the SID of an allowed or denied ACE begins at
    ``sizeof(_Ace)``. Object ACEs keep their mask in the same place but put a
    pair of GUIDs before the SID, which is why the policy refuses them instead
    of reading a SID from that offset.
    """

    _fields_ = [
        ("ace_type", ctypes.c_ubyte),
        ("ace_flags", ctypes.c_ubyte),
        ("ace_size", ctypes.c_ushort),
        ("mask", ctypes.c_uint32),
    ]


class _Acl(ctypes.Structure):  # pragma: no cover - needs Windows
    """The fixed part of an ``ACL`` structure."""

    _fields_ = [
        ("acl_revision", ctypes.c_ubyte),
        ("sbz1", ctypes.c_ubyte),
        ("acl_size", ctypes.c_ushort),
        ("ace_count", ctypes.c_ushort),
        ("sbz2", ctypes.c_ushort),
    ]


class _SidAndAttributes(ctypes.Structure):  # pragma: no cover - needs Windows
    """One ``SID_AND_ATTRIBUTES`` entry."""

    _fields_ = [
        ("sid", ctypes.c_void_p),
        ("attributes", ctypes.c_uint32),
    ]


class _TokenUser(ctypes.Structure):  # pragma: no cover - needs Windows
    """The ``TOKEN_USER`` payload of a token query."""

    _fields_ = [("user", _SidAndAttributes)]
