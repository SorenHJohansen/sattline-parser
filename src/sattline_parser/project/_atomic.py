"""Filesystem primitives shared by the project caches.

Both caches write through a temporary file next to the target and then
``os.replace`` it into place. The temporary name must be unique per writer, or
two processes sharing a cache directory can truncate each other's file and a
concurrent prune can delete one that is still being written.

:class:`PrivateDirectory` is the privacy boundary both caches share. It is
opened once, records the identity of the directory it holds, and performs every
entry operation relative to that recorded identity. A directory renamed and
replaced after construction is refused rather than written into, and a link is
never followed. The platform policy itself lives in
:func:`sattline_parser.source_io.private_cache_dir`; this class holds the
descriptor and revalidates it.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import stat
import time
from pathlib import Path

from sattline_parser.source_io import private_cache_dir

__all__ = [
    "TEMP_FILE_MAX_AGE_SECONDS",
    "TEMP_SUFFIX",
    "PrivateDirectory",
    "temp_file_is_abandoned",
    "temp_name_for",
    "temp_path_for",
]

TEMP_SUFFIX = ".tmp"

#: A temporary file younger than this may belong to a running writer, so a
#: cleanup pass leaves it alone.
TEMP_FILE_MAX_AGE_SECONDS = 3600.0

#: Whether this platform can hold a directory descriptor. Windows cannot open a
#: directory portably, so the same operations run by path there; the policy is
#: identical, only the mechanism differs. Resolved once at import so the tests
#: can drive the path form on any platform.
_USES_DIRECTORY_DESCRIPTOR = os.name == "posix"

#: The descriptor flags every directory and entry open uses. ``O_NOFOLLOW`` is
#: absent on Windows, where the privacy check rejects a reparse point instead.
_DIRECTORY_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)
#: The descriptor flags every entry open uses. ``O_NONBLOCK`` makes the open
#: return instead of waiting: a FIFO entry with no writer would otherwise block
#: before the regular-file check could refuse it. ``O_NOFOLLOW`` is absent on
#: Windows, where the privacy check rejects a reparse point instead.
_ENTRY_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)

#: A single cache entry larger than this is refused instead of read into
#: memory. An AST pickle for a very large unit is far below it.
MAX_ENTRY_BYTES = 64 * 1024 * 1024


def temp_name_for(name: str) -> str:
    """A unique temporary sibling name for *name*, safe for concurrent writers."""
    return f"{name}.{os.getpid()}.{secrets.token_hex(8)}{TEMP_SUFFIX}"


def temp_path_for(path: Path) -> Path:
    """A unique sibling temporary path for ``path``, safe for concurrent writers."""
    return path.with_name(temp_name_for(path.name))


def temp_file_is_abandoned(path: Path) -> bool:
    """True when a temporary file is old enough that no writer can still own it."""
    try:
        stat_result = path.stat()
    except OSError:
        return True
    return time.time() - stat_result.st_mtime >= TEMP_FILE_MAX_AGE_SECONDS


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except OSError:
        return None


def _read_all(descriptor: int) -> bytes | None:
    """Read a whole file from *descriptor*, refusing a non-regular entry."""
    try:
        info = os.fstat(descriptor)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ENTRY_BYTES:
        return None
    chunks: list[bytes] = []
    try:
        while True:
            chunk = os.read(descriptor, 1 << 16)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError:
        return None


def _read_prefix(descriptor: int, limit: int) -> bytes | None:
    """Read at most *limit* bytes from *descriptor*."""
    chunks: list[bytes] = []
    remaining = limit
    try:
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 1 << 16))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError:
        return None
    return b"".join(chunks)


def _write_all(descriptor: int, data: bytes) -> bool:
    """Write and flush *data* to *descriptor*, returning whether it reached disk."""
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, ValueError):
        # A closed or bad descriptor is a failed cache write, not a load
        # failure; the caller treats ``False`` as a miss.
        return False
    return True


class PrivateDirectory:
    """A cache directory proven private, revalidated before every operation.

    POSIX keeps a descriptor opened ``O_DIRECTORY | O_NOFOLLOW`` and records
    ``(st_dev, st_ino)``. Every entry operation is relative to that descriptor
    and never follows a link, so a directory that is renamed and replaced after
    construction is refused instead of written into. Revalidation compares the
    held descriptor with the entry the recorded path still names and rechecks
    owner and mode, which is what makes the "validated on every write" claim
    true.

    Windows cannot open a directory descriptor portably, so it re-reads the
    security descriptor through :func:`private_cache_dir` on every revalidation
    instead. The policy is the same; only the mechanism differs.
    """

    def __init__(
        self,
        path: Path,
        *,
        descriptor: int | None,
        identity: tuple[int, int],
        owner: int,
        parent: PrivateDirectory | None = None,
        name: str | None = None,
    ) -> None:
        self.path = path
        self._descriptor = descriptor
        self._identity = identity
        self._owner = owner
        self._parent = parent
        self._name = name
        self._closed = False

    @classmethod
    def open(cls, path: Path, *, create: bool) -> PrivateDirectory | None:
        """Open *path* as a private directory, or return ``None``.

        The platform policy runs first (:func:`private_cache_dir`), so a
        symlink, a foreign owner, an open mode, or an unproven Windows DACL
        yields ``None``. On POSIX the descriptor is then verified to be the
        same directory the policy just accepted, which closes the swap window
        between the check and the open.
        """
        validated = private_cache_dir(path, create=create)
        if validated is None:
            return None
        info = _lstat(validated)
        if info is None or not stat.S_ISDIR(info.st_mode):
            return None
        identity = (info.st_dev, info.st_ino)
        if not _USES_DIRECTORY_DESCRIPTOR:
            return cls(validated, descriptor=None, identity=identity, owner=info.st_uid)
        try:
            descriptor = os.open(validated, _DIRECTORY_FLAGS)
        except OSError:
            return None
        opened = _fstat(descriptor)
        if opened is None or (opened.st_dev, opened.st_ino) != identity:
            os.close(descriptor)
            return None
        return cls(validated, descriptor=descriptor, identity=identity, owner=info.st_uid)

    @classmethod
    def child(cls, parent: PrivateDirectory, name: str, *, create: bool) -> PrivateDirectory | None:
        """Open ``name`` under *parent* as a private directory.

        POSIX creates the level ``0700`` relative to the held descriptor and
        opens it with ``O_NOFOLLOW``, so a planted link is refused. Windows uses
        the path-based policy, where a reparse point is refused by the privacy
        check.
        """
        if parent._descriptor is None:
            return cls.open(parent.path / name, create=create)
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent._descriptor)
            except FileExistsError:
                pass
            except OSError:
                return None
        try:
            descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent._descriptor)
        except OSError:
            return None
        info = _fstat(descriptor)
        if info is None or not stat.S_ISDIR(info.st_mode) or info.st_uid != parent._owner:
            os.close(descriptor)
            return None
        if info.st_mode & 0o077:
            if not create or not _chmod_private(name, parent._descriptor):
                os.close(descriptor)
                return None
            info = _fstat(descriptor)
            if info is None or info.st_mode & 0o077:
                os.close(descriptor)
                return None
        return cls(
            parent.path / name,
            descriptor=descriptor,
            identity=(info.st_dev, info.st_ino),
            owner=info.st_uid,
            parent=parent,
            name=name,
        )

    def revalidate(self) -> bool:
        """Whether this handle still names the private directory it recorded.

        The held descriptor must be the recorded directory, the recorded name
        must still resolve to that directory, the owner must be unchanged, and
        the mode must still carry no group or world bits. Any doubt is a
        refusal: a cache is an optimisation and must fail closed.
        """
        if self._closed:
            return False
        if self._descriptor is None:
            return private_cache_dir(self.path, create=False) is not None
        info = _fstat(self._descriptor)
        if info is None or not stat.S_ISDIR(info.st_mode):
            return False
        if (info.st_dev, info.st_ino) != self._identity or info.st_uid != self._owner:
            return False
        if info.st_mode & 0o077:
            return False
        named = self._stat_name()
        if named is None or (named.st_dev, named.st_ino) != self._identity:
            return False
        return self._parent is None or self._parent.revalidate()

    def read(self, name: str) -> bytes | None:
        """Read entry *name* without following a link, or return ``None``."""
        if self._closed:
            return None
        if self._descriptor is None:
            info = _lstat(self.path / name)
            if info is None or not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ENTRY_BYTES:
                return None
            try:
                return (self.path / name).read_bytes()
            except OSError:
                return None
        try:
            descriptor = os.open(name, _ENTRY_FLAGS, dir_fd=self._descriptor)
        except OSError:
            return None
        try:
            return _read_all(descriptor)
        finally:
            os.close(descriptor)

    def read_prefix(self, name: str, limit: int) -> bytes | None:
        """Read at most *limit* bytes of entry *name* without following a link."""
        if self._closed:
            return None
        if self._descriptor is None:
            info = _lstat(self.path / name)
            if info is None or not stat.S_ISREG(info.st_mode):
                return None
            try:
                with (self.path / name).open("rb") as handle:
                    return handle.read(limit)
            except OSError:
                return None
        try:
            descriptor = os.open(name, _ENTRY_FLAGS, dir_fd=self._descriptor)
        except OSError:
            return None
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                return None
            return _read_prefix(descriptor, limit)
        finally:
            os.close(descriptor)

    def write_atomic(self, name: str, data: bytes) -> None:
        """Publish *data* under *name* atomically, relative to the held directory."""
        if self._closed:
            raise OSError("cache directory handle is closed")
        temp_name = temp_name_for(name)
        if self._descriptor is None:
            target = self.path / name
            temp_path = self.path / temp_name
            try:
                descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                if not _write_all(descriptor, data):
                    raise OSError("cache entry could not be written")
                os.replace(temp_path, target)
            except OSError:
                self.unlink(temp_name)
                raise
            return
        try:
            descriptor = os.open(
                temp_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=self._descriptor,
            )
            if not _write_all(descriptor, data):
                raise OSError("cache entry could not be written")
            os.replace(temp_name, name, src_dir_fd=self._descriptor, dst_dir_fd=self._descriptor)
        except OSError:
            self.unlink(temp_name)
            raise

    def create_exclusive(self, name: str, data: bytes) -> bool:
        """Create *name* exclusively with *data*; raise ``FileExistsError`` if taken.

        The bytes are written and flushed to disk before the call returns, so a
        caller can publish the complete file. A write failure removes the file
        this call created, never one another writer owns.
        """
        try:
            descriptor = self._open_exclusive(name)
        except FileExistsError:
            raise
        except OSError:
            return False
        if _write_all(descriptor, data):
            return True
        self.unlink(name)
        return False

    def link(self, source: str, target: str) -> None:
        """Hard-link *source* to *target* inside the held directory.

        Raises ``FileExistsError`` when *target* exists, so a caller can read
        the winner's file instead of replacing it, and ``OSError`` when the
        filesystem has no hard links. Windows has no ``dir_fd`` for links, so it
        links by path under a directory already proven private.
        """
        if self._descriptor is None:
            os.link(self.path / source, self.path / target)
            return
        os.link(source, target, src_dir_fd=self._descriptor, dst_dir_fd=self._descriptor)

    def unlink(self, name: str) -> bool:
        """Remove entry *name*, returning whether it was removed."""
        if self._closed:
            return False
        try:
            if self._descriptor is None:
                (self.path / name).unlink()
            else:
                os.unlink(name, dir_fd=self._descriptor)
        except OSError:
            return False
        return True

    def names(self) -> list[str]:
        """Every entry name in the directory, or an empty list when unreadable."""
        if self._closed:
            return []
        try:
            if self._descriptor is None:
                return sorted(entry.name for entry in self.path.iterdir())
            return os.listdir(self._descriptor)
        except OSError:
            return []

    def stat(self, name: str) -> os.stat_result | None:
        """``lstat`` entry *name*, never following a link."""
        if self._closed:
            return None
        try:
            if self._descriptor is None:
                return (self.path / name).lstat()
            return os.stat(name, dir_fd=self._descriptor, follow_symlinks=False)
        except OSError:
            return None

    def touch(self, name: str) -> None:
        """Update entry *name*'s mtime, ignoring a failure."""
        try:
            if self._descriptor is None:
                os.utime(self.path / name, None)
            else:
                os.utime(name, None, dir_fd=self._descriptor)
        except OSError:
            pass

    def close(self) -> None:
        """Release the held descriptor, if any."""
        self._closed = True
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)

    def __del__(self) -> None:
        # The descriptor is a process resource, not memory, so releasing it must
        # not wait for a garbage-collection cycle that may never run.
        with contextlib.suppress(Exception):
            self.close()

    def _stat_name(self) -> os.stat_result | None:
        if self._descriptor is None:  # pragma: no cover - Windows opens no descriptor
            return _lstat(self.path)
        if self._parent is None or self._name is None:
            return _lstat(self.path)
        parent_descriptor = self._parent._descriptor
        if parent_descriptor is None:  # pragma: no cover - Windows opens no descriptor
            return _lstat(self.path)
        try:
            return os.stat(self._name, dir_fd=parent_descriptor, follow_symlinks=False)
        except OSError:
            return None

    def _open_exclusive(self, name: str) -> int:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        if self._descriptor is None:  # pragma: no cover - Windows opens no descriptor
            return os.open(self.path / name, flags, 0o600)
        return os.open(name, flags, 0o600, dir_fd=self._descriptor)


def _fstat(descriptor: int) -> os.stat_result | None:
    try:
        return os.fstat(descriptor)
    except OSError:
        return None


def _chmod_private(name: str, parent_descriptor: int) -> bool:
    try:
        os.chmod(name, 0o700, dir_fd=parent_descriptor)
    except OSError:
        return False
    return True
