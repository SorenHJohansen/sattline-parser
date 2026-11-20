"""Run pytest with the current user as the default Windows object owner."""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Any, cast

import pytest

_TOKEN_QUERY = 0x0008
_TOKEN_ADJUST_DEFAULT = 0x0080
_TOKEN_USER = 1
_TOKEN_OWNER = 4


def _set_default_owner() -> None:
    if os.name != "nt":
        raise RuntimeError("windows_pytest requires Windows")
    windll = cast(Any, ctypes.WinDLL)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    advapi32 = windll("advapi32", use_last_error=True)
    kernel32 = windll("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    advapi32.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    advapi32.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    advapi32.GetTokenInformation.restype = ctypes.c_int
    advapi32.SetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    advapi32.SetTokenInformation.restype = ctypes.c_int
    token = ctypes.c_void_p()
    win_error = cast(Any, ctypes.WinError)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    last_error = cast(Any, ctypes.get_last_error)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY | _TOKEN_ADJUST_DEFAULT, ctypes.byref(token)
    ):
        raise win_error(last_error())
    try:
        size = ctypes.c_uint32()
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
        if not size.value:
            raise win_error(last_error())
        user = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, _TOKEN_USER, user, size.value, ctypes.byref(size)):
            raise win_error(last_error())
        owner = ctypes.cast(user, ctypes.POINTER(ctypes.c_void_p)).contents
        if not advapi32.SetTokenInformation(token, _TOKEN_OWNER, ctypes.byref(owner), ctypes.sizeof(owner)):
            raise win_error(last_error())
    finally:
        kernel32.CloseHandle(token)


if __name__ == "__main__":
    _set_default_owner()
    raise SystemExit(pytest.main(sys.argv[1:]))
