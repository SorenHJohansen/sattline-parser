# pyright: reportPrivateUsage=false
"""Privacy-boundary tests for the per-file AST cache.

The cache directory is the security boundary: whoever can replace it can plant
both the HMAC key and a matching pickle. These tests prove that a directory
renamed and replaced after the handle is constructed is refused, that entry and
key reads never follow a link, and that the entry cap and vanished-source prune
behave as the documentation says.

No second uid is needed for the swap tests: the handle records the identity of
the directory it opened, so replacing the name is enough. The end-to-end
foreign-owner test uses a user namespace when the platform provides one and is
skipped otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.api import parse_source_file
from sattline_parser.project import FileASTCache
from sattline_parser.project._atomic import PrivateDirectory
from sattline_parser.project.ast_cache import (
    _PICKLE_HMAC_KEY_NAME,
    _is_regular_file,
    _read_entry_header,
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


def _write_code(directory: Path, name: str = "Prog.s") -> Path:
    path = directory / name
    path.write_bytes(_MINIMAL_SOURCE.encode("utf-8"))
    return path


def _entries(cache: FileASTCache) -> list[Path]:
    return sorted(cache.cache_dir.glob("*.pickle"))


def _swap_directory(cache: FileASTCache) -> Path:
    """Rename the cache directory away and leave an empty directory in its place."""
    original = cache.cache_dir.parent / "original"
    shutil.move(cache.cache_dir, original)
    cache.cache_dir.mkdir()
    return original


def test_a_renamed_and_replaced_cache_root_is_refused_by_load_and_save(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    code_path = _write_code(tmp_path)
    cache = FileASTCache(cache_root)
    assert cache.enabled
    picture = parse_source_file(code_path)
    cache.save(code_path, "draft", picture)
    assert cache.load(code_path, "draft") is not None
    original = _swap_directory(cache)

    assert cache.load(code_path, "draft") is None
    cache.save(code_path, "draft", picture)

    assert not cache.enabled
    assert list(cache.cache_dir.iterdir()) == []
    assert len(list(original.glob("*.pickle"))) == 1


def test_a_replaced_leaf_directory_is_refused(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    picture = parse_source_file(code_path)
    cache.save(code_path, "draft", picture)
    original = tmp_path / "file_ast-original"
    cache.cache_dir.rename(original)
    cache.cache_dir.mkdir()

    assert cache.load(code_path, "draft") is None
    cache.save(code_path, "draft", picture)

    assert not cache.enabled
    assert list(cache.cache_dir.iterdir()) == []
    assert len(list(original.glob("*.pickle"))) == 1


def test_a_symlink_replacing_the_cache_name_is_refused(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    code_path = _write_code(tmp_path)
    picture = parse_source_file(code_path)
    cache.save(code_path, "draft", picture)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    shutil.rmtree(cache.cache_dir)
    cache.cache_dir.symlink_to(replacement, target_is_directory=True)

    assert cache.load(code_path, "draft") is None
    assert not cache.enabled
    cache.save(code_path, "draft", picture)
    assert list(replacement.iterdir()) == []


def test_a_widened_directory_mode_is_refused(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    picture = parse_source_file(code_path)
    cache.save(code_path, "draft", picture)
    os.chmod(cache.cache_dir, 0o755)

    assert cache.load(code_path, "draft") is None
    assert not cache.enabled


def test_every_save_revalidates_the_held_directory(tmp_path: Path) -> None:
    """A save writes nothing once the recorded identity no longer matches."""
    cache = FileASTCache(tmp_path)
    code_path = _write_code(tmp_path)
    picture = parse_source_file(code_path)
    cache.save(code_path, "draft", picture)
    original = _swap_directory(cache)
    before = len(list(original.glob("*.pickle")))

    cache.save(code_path, "official", picture)

    assert not cache.enabled
    assert len(list(original.glob("*.pickle"))) == before
    assert list(cache.cache_dir.iterdir()) == []


def test_a_symlinked_key_file_is_refused(tmp_path: Path) -> None:
    """The key is read through the descriptor with ``O_NOFOLLOW``."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    picture = parse_source_file(code_path)
    cache.save(code_path, "draft", picture)
    key_path = cache.cache_dir / _PICKLE_HMAC_KEY_NAME
    outside = tmp_path / "outside-key"
    shutil.move(key_path, outside)
    key_path.symlink_to(outside)

    assert cache.load(code_path, "draft") is None
    cache.save(code_path, "official", picture)

    assert len(_entries(cache)) == 1


def test_a_swapped_key_does_not_authenticate_the_entry(tmp_path: Path) -> None:
    """A different key in the same directory makes every existing entry a miss."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    picture = parse_source_file(code_path)
    cache.save(code_path, "draft", picture)
    (cache.cache_dir / _PICKLE_HMAC_KEY_NAME).write_bytes(b"k" * 32)

    assert cache.load(code_path, "draft") is None


def test_a_read_only_handle_refuses_a_replaced_directory(tmp_path: Path) -> None:
    writer = FileASTCache(tmp_path)
    code_path = _write_code(tmp_path)
    writer.save(code_path, "draft", parse_source_file(code_path))
    reader = FileASTCache(tmp_path, read_only=True)
    _swap_directory(reader)

    assert reader.load(code_path, "draft") is None
    assert not reader.enabled


def test_a_cache_under_a_group_writable_parent_is_disabled(tmp_path: Path) -> None:
    """Whoever can write a parent can replace the whole cache tree."""
    shared = tmp_path / "shared"
    shared.mkdir()
    os.chmod(shared, 0o777)
    try:
        cache = FileASTCache(shared / "cache")
        assert not cache.enabled
    finally:
        os.chmod(shared, 0o700)


def test_prune_reads_the_signed_header_without_unpickling(tmp_path: Path) -> None:
    """A vanished source is dropped from the header alone, never from a pickle."""
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", parse_source_file(code_path))
    code_path.unlink()

    with patch(f"{_AC_PATH}.pickle.loads", side_effect=AssertionError("must not unpickle when pruning")):
        removed = cache.prune_stale_entries()

    assert removed == 1
    assert _entries(cache) == []


def test_prune_never_stats_an_unverified_source_path(tmp_path: Path) -> None:
    """A header this cache did not sign is not trusted, so its path is not touched."""
    cache = FileASTCache(tmp_path)
    name = f"{cache._identity}-{'0' * 64}.pickle"
    (cache.cache_dir / name).write_bytes(b"not a signed entry")

    with patch(f"{_AC_PATH}._is_regular_file", side_effect=AssertionError("must not stat an untrusted path")):
        assert cache.prune_stale_entries() == 0

    assert (cache.cache_dir / name).is_file()
    assert _is_regular_file(cache.cache_dir / name)


def test_a_vanished_source_entry_keeps_a_present_one(tmp_path: Path) -> None:
    present = _write_code(tmp_path, "Present.s")
    gone = _write_code(tmp_path, "Gone.s")
    cache = FileASTCache(tmp_path)
    cache.save(present, "draft", parse_source_file(present))
    cache.save(gone, "draft", parse_source_file(gone))
    gone.unlink()

    assert cache.prune_stale_entries() == 1
    assert len(_entries(cache)) == 1
    assert cache.load(present, "draft") is not None


def test_the_entry_cap_is_enforced_during_a_run(tmp_path: Path) -> None:
    """One long run cannot leave the directory past the cap plus one batch."""
    cache = FileASTCache(tmp_path, max_entries=4)
    for index in range(10):
        code_path = _write_code(tmp_path, f"U{index}.s")
        cache.save(code_path, "draft", parse_source_file(code_path))

    assert len(_entries(cache)) <= 4


def test_the_entry_cap_interval_is_bounded(tmp_path: Path) -> None:
    assert FileASTCache(tmp_path, max_entries=0)._cap_check_interval() == 1
    assert FileASTCache(tmp_path, max_entries=4)._cap_check_interval() == 1
    assert FileASTCache(tmp_path, max_entries=1024)._cap_check_interval() == 64
    assert FileASTCache(tmp_path, max_entries=200)._cap_check_interval() == 25


def test_a_closed_handle_refuses_every_operation(tmp_path: Path) -> None:
    directory = PrivateDirectory.open(tmp_path, create=True)
    assert directory is not None
    directory.close()

    assert not directory.revalidate()
    assert directory.read("anything") is None
    assert directory.read_prefix("anything", 10) is None
    assert directory.names() == []
    assert directory.stat("anything") is None
    assert not directory.unlink("anything")
    directory.touch("anything")
    with pytest.raises(OSError, match="closed"):
        directory.write_atomic("anything", b"x")


def test_the_closed_handle_never_falls_back_to_a_path(tmp_path: Path) -> None:
    """A closed POSIX handle must not silently reopen by path."""
    directory = PrivateDirectory.open(tmp_path, create=True)
    assert directory is not None
    directory.close()

    assert not directory.revalidate()


def test_a_symlinked_entry_is_never_followed(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", parse_source_file(code_path))
    entry = cache._path(code_path, "draft")
    outside = tmp_path / "outside.pickle"
    entry.replace(outside)
    entry.symlink_to(outside)

    assert cache.load(code_path, "draft") is None
    assert _read_entry_header(cache._directory, entry.name) is None  # type: ignore[arg-type]


def _subuid_start() -> int | None:
    """The first subordinate uid this user may map, or ``None``."""
    try:
        lines = Path("/etc/subuid").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.split(":")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit() and int(parts[2]) > 0:
            return int(parts[1])
    return None


def _namespace_command(script: str) -> list[str]:
    """A user-namespace command that maps this user and one second uid."""
    subuid = _subuid_start()
    assert subuid is not None
    return [
        "unshare",
        "--user",
        f"--map-users=0:{os.getuid()}:1",
        f"--map-users=1:{subuid}:1",
        f"--map-groups=0:{os.getgid()}:1",
        f"--map-groups=1:{subuid}:1",
        sys.executable,
        "-c",
        script,
    ]


def _second_uid_available() -> bool:
    """Whether a user namespace can map a second uid for the forgery test."""
    if os.name != "posix" or shutil.which("unshare") is None or _subuid_start() is None:
        return False
    try:
        result = subprocess.run(
            _namespace_command("import os; os.setgid(1); os.setuid(1); print(os.getuid())"),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "1"


_SECOND_UID = _second_uid_available()


@pytest.mark.skipif(not _SECOND_UID, reason="needs a user namespace that can map a second uid")
def test_a_cache_planted_by_another_uid_is_refused(tmp_path: Path) -> None:
    """End to end: a cache root owned by another uid is refused, key and all.

    The namespace maps inner uid 0 to this user and inner uid 1 to a subuid, so a
    real second uid plants a cache directory with its own key. The victim must
    refuse it instead of reading a payload that uid signed.
    """
    shared = Path(tempfile.mkdtemp(prefix="sattline-forge-", dir=tempfile.gettempdir()))
    os.chmod(shared, 0o777)
    forged = shared / "cache" / "file_ast"
    try:
        create = (
            "import os\n"
            "os.setgid(1)\n"
            "os.setuid(1)\n"
            f"os.makedirs({str(forged)!r}, mode=0o700)\n"
            f"os.chmod({str(forged)!r}, 0o755)\n"
            f"open({str(forged / _PICKLE_HMAC_KEY_NAME)!r}, 'wb').write(b'k' * 32)\n"
        )
        result = subprocess.run(
            _namespace_command(create),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"could not create the forged cache: {result.stderr.strip()}")

        code_path = _write_code(tmp_path)
        cache = FileASTCache(shared / "cache")

        assert not cache.enabled
        assert cache.load(code_path, "draft") is None
        cache.save(code_path, "draft", parse_source_file(code_path))
        assert list(forged.glob("*.pickle")) == []
        assert (forged / _PICKLE_HMAC_KEY_NAME).read_bytes() == b"k" * 32
    finally:
        # The forged tree belongs to the second uid, so only that uid can empty it.
        subprocess.run(
            _namespace_command(
                "import os, shutil\n"
                "os.setgid(1)\n"
                "os.setuid(1)\n"
                f"shutil.rmtree({str(shared / 'cache')!r}, ignore_errors=True)\n"
            ),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        shutil.rmtree(shared, ignore_errors=True)
