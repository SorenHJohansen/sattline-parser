"""Parser-owned per-file AST cache (plan §6, Q7).

Each parsed ``BasePicture`` is stored in an HMAC-signed pickle envelope keyed by
code path and source mode. The cache namespace and version belong to
``sattline-parser`` (``FILE_AST_CACHE_VERSION``, a distinct file-format magic),
so parser- and SattLint-written cache files never cross-read. Path, mode, and a
``mtime_ns`` + ``size`` stat snapshot are validated before a cached AST is
trusted; entries outside the parser namespace are pruned.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import pickle  # nosec B403 - HMAC-signed pickle envelope, key creation racy/excl guarded
import secrets
from pathlib import Path
from typing import cast

from sattline_parser.models.ast_model import BasePicture

FILE_AST_CACHE_VERSION = 1

_PICKLE_CACHE_MAGIC = b"SATTLINE-PARSER-PICKLE-V1\n"
_PICKLE_HMAC_KEY_NAME = ".pickle-hmac-key"
_PICKLE_HMAC_SIZE = 32
_PICKLE_KEY_DIR_NAME = "file_ast"

_ALLOWED_PICKLE_LOADER_ERRORS = (
    pickle.UnpicklingError,
    AttributeError,
    EOFError,
    ImportError,
    IndexError,
    TypeError,
    ValueError,
)


def _remove_file(path: Path) -> bool:
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def _as_data_dict(value: object) -> dict[object, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[object, object], value)


def _matches_stat_snapshot(path: Path, *, mtime_ns: object, size: object) -> bool:
    if not isinstance(mtime_ns, int) or not isinstance(size, int):
        return False
    stat_result = _safe_stat(path)
    if stat_result is None:
        return False
    return stat_result.st_mtime_ns == mtime_ns and stat_result.st_size == size


def _code_path_key(code_path: Path) -> str:
    """A stable cache identity for a code path.

    Resolves the path so the same file reached via a symlink, relative path, or
    alternate spelling shares one cache entry and one meta validation.
    """
    try:
        return str(code_path.resolve())
    except OSError:
        return str(code_path)


def _pickle_hmac_key_path(directory: Path) -> Path:
    return directory / _PICKLE_HMAC_KEY_NAME


def _read_pickle_hmac_key(path: Path) -> bytes | None:
    try:
        key = path.read_bytes()
    except OSError:
        return None
    if len(key) != _PICKLE_HMAC_SIZE:
        return None
    return key


def _load_or_create_pickle_hmac_key(directory: Path) -> bytes | None:
    key_path = _pickle_hmac_key_path(directory)
    existing_key = _read_pickle_hmac_key(key_path)
    if existing_key is not None:
        return existing_key
    if key_path.exists() and not _remove_file(key_path):
        return None
    directory.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(_PICKLE_HMAC_SIZE)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(key_path, flags, 0o600)
    except FileExistsError:
        return _read_pickle_hmac_key(key_path)
    except OSError:
        return None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        _remove_file(key_path)
        return None
    return key


def _read_signed_pickle_envelope(payload_bytes: bytes) -> tuple[str | None, bytes]:
    if not payload_bytes.startswith(_PICKLE_CACHE_MAGIC):
        return None, b""
    remainder = payload_bytes[len(_PICKLE_CACHE_MAGIC) :]
    signature, separator, pickled_payload = remainder.partition(b"\n")
    digest_size = hashlib.sha256().digest_size * 2
    if separator != b"\n" or len(signature) != digest_size:
        return None, b""
    try:
        return signature.decode("ascii"), pickled_payload
    except UnicodeDecodeError:
        return None, b""


def _load_pickle_payload(path: Path) -> object | None:
    try:
        payload_bytes = path.read_bytes()
    except OSError:
        return None
    signature, pickled_payload = _read_signed_pickle_envelope(payload_bytes)
    if signature is None:
        return None
    key = _load_or_create_pickle_hmac_key(path.parent)
    if key is None:
        return None
    expected_signature = hmac.new(key, pickled_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    try:
        return pickle.loads(pickled_payload)  # nosec B301 - payload HMAC-verified above
    except _ALLOWED_PICKLE_LOADER_ERRORS:
        return None


def _save_pickle_payload(path: Path, payload: object) -> None:
    key = _load_or_create_pickle_hmac_key(path.parent)
    if key is None:
        raise OSError(f"Could not create pickle HMAC key for {path.parent}")
    pickled_payload = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    signature = hmac.new(key, pickled_payload, hashlib.sha256).hexdigest().encode("ascii")
    temp_path = path.with_name(f"{path.name}.tmp")
    try:
        with temp_path.open("wb") as handle:
            handle.write(_PICKLE_CACHE_MAGIC)
            handle.write(signature)
            handle.write(b"\n")
            handle.write(pickled_payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError:
        _remove_file(temp_path)
        raise


class FileASTCache:
    """Per-file AST cache keyed by code path and source mode.

    The backing store lives under ``<cache_dir>/file_ast`` so it never collides
    with the file-lookup cache or with a borrowed SattLint cache directory.
    """

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir / _PICKLE_KEY_DIR_NAME
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._startup_pruned_entries = self.prune_stale_entries()

    @staticmethod
    def _key(code_path: Path, mode: str) -> str:
        digest = hashlib.sha256()
        digest.update(_code_path_key(code_path).encode("utf-8", errors="ignore"))
        digest.update(mode.encode("utf-8", errors="ignore"))
        return digest.hexdigest()

    def _path(self, code_path: Path, mode: str) -> Path:
        return self.cache_dir / f"{self._key(code_path, mode)}.pickle"

    def load(self, code_path: Path, mode: str) -> BasePicture | None:
        """Return the cached AST for ``code_path``/``mode``, or ``None``.

        ``None`` means either no entry exists or the entry failed validation
        (foreign namespace, wrong version, tampered payload, changed source).
        """
        path = self._path(code_path, mode)
        if not path.exists():
            return None
        payload = _load_pickle_payload(path)
        payload_map = _as_data_dict(payload)
        if payload_map is None or payload_map.get("version") != FILE_AST_CACHE_VERSION:
            return None
        meta = _as_data_dict(payload_map.get("meta"))
        if meta is None:
            return None
        if meta.get("path") != _code_path_key(code_path):
            return None
        if meta.get("mode") != mode:
            return None
        if not _matches_stat_snapshot(code_path, mtime_ns=meta.get("mtime_ns"), size=meta.get("size")):
            return None
        ast = payload_map.get("ast")
        if not isinstance(ast, BasePicture):
            return None
        return ast

    def save(self, code_path: Path, mode: str, ast: BasePicture) -> None:
        stat_result = _safe_stat(code_path)
        if stat_result is None:
            return
        payload: dict[str, object] = {
            "version": FILE_AST_CACHE_VERSION,
            "meta": {
                "path": _code_path_key(code_path),
                "mode": mode,
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
            },
            "ast": ast,
        }
        _save_pickle_payload(self._path(code_path, mode), payload)

    def prune_stale_entries(self) -> int:
        """Remove entries that are not valid current-namespace AST entries.

        Returns the number of entries removed.
        """
        removed = 0
        directory = self.cache_dir
        if not directory.exists():
            return 0
        for path in directory.iterdir():
            if not path.is_file():
                continue
            if path.name.endswith(".pickle.tmp"):
                _remove_file(path)
                removed += 1
                continue
            if not path.name.endswith(".pickle"):
                continue
            payload = _load_pickle_payload(path)
            payload_map = _as_data_dict(payload)
            if payload_map is not None and payload_map.get("version") == FILE_AST_CACHE_VERSION:
                continue
            if _remove_file(path):
                removed += 1
        return removed

    def drain_startup_pruned_entries(self) -> int:
        """Return (and reset) the count of entries pruned at construction time."""
        removed = self._startup_pruned_entries
        self._startup_pruned_entries = 0
        return removed


__all__ = ["FILE_AST_CACHE_VERSION", "FileASTCache"]
