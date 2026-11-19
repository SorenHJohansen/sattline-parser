# pyright: reportPrivateUsage=false
"""Tests for the parser cache boundary and the on-disk Lark cache write.

Two boundaries are pinned here. ``private_cache_dir`` proves a cache level and
every directory above it private, so a parent another user can write disables
the cache. ``build_lark_parser`` writes the Lark cache through a private staging
file and publishes it with ``os.replace``, so no reader observes a partial
pickle; a truncated cache is still discarded and rebuilt, as before.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser import source_io
from sattline_parser.source_io import (
    _ancestor_chain_is_private,
    _ancestor_is_private,
    _lark_cache_header,
    _lark_staging_path,
    build_lark_parser,
    parse_source_text,
    private_cache_dir,
)

_OWN_UID = os.getuid() if hasattr(os, "getuid") else 1000


def _directory_info(*, uid: int, mode: int, inode: int = 1) -> os.stat_result:
    return os.stat_result((stat.S_IFDIR | mode, inode, 1, 1, uid, uid, 0, 0, 0, 0))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_an_owned_directory_without_group_or_world_write_is_private() -> None:
    assert _ancestor_is_private(_directory_info(uid=_OWN_UID, mode=0o755))
    assert _ancestor_is_private(_directory_info(uid=_OWN_UID, mode=0o700))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_a_group_writable_directory_is_not_private_even_when_owned() -> None:
    """Another member of the group can replace a tree below it."""
    assert not _ancestor_is_private(_directory_info(uid=_OWN_UID, mode=0o775))
    assert not _ancestor_is_private(_directory_info(uid=_OWN_UID, mode=0o1777))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_a_root_owned_directory_is_private() -> None:
    assert _ancestor_is_private(_directory_info(uid=0, mode=0o755))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_a_root_owned_sticky_directory_is_private() -> None:
    """The shared temporary directory is safe: nobody else can rename our entry."""
    assert _ancestor_is_private(_directory_info(uid=0, mode=0o1777))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_a_root_owned_directory_open_to_everyone_is_not_private() -> None:
    assert not _ancestor_is_private(_directory_info(uid=0, mode=0o777))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_a_foreign_owned_directory_is_not_private() -> None:
    assert not _ancestor_is_private(_directory_info(uid=_OWN_UID + 1, mode=0o755))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_no_owner_check_means_no_private_ancestor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source_io, "_getuid", None)

    assert not _ancestor_is_private(_directory_info(uid=_OWN_UID, mode=0o700))


def test_a_private_directory_chain_is_accepted(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert _ancestor_chain_is_private(nested)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_a_group_writable_parent_refuses_the_chain(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    os.chmod(shared, 0o777)
    try:
        assert not _ancestor_chain_is_private(shared / "cache")
    finally:
        os.chmod(shared, 0o700)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_a_missing_parent_refuses_the_chain(tmp_path: Path) -> None:
    assert not _ancestor_chain_is_private(tmp_path / "missing" / "cache")


def test_windows_proves_the_parent_chain_through_the_descriptor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows ACLs already inherit down the chain, so the walk does not apply."""
    monkeypatch.setattr(source_io, "_IS_WINDOWS", True)

    assert _ancestor_chain_is_private(Path("/does/not/exist"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner and mode bits")
def test_private_cache_dir_refuses_a_root_under_a_writable_parent(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    os.chmod(shared, 0o777)
    try:
        assert private_cache_dir(shared / "cache") is None
    finally:
        os.chmod(shared, 0o700)


def test_private_cache_dir_accepts_a_private_parent(tmp_path: Path) -> None:
    directory = tmp_path / "cache"

    assert private_cache_dir(directory) == directory
    if os.name == "posix":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_lark_staging_paths_are_unique_siblings(tmp_path: Path) -> None:
    shared = tmp_path / "cache.lark"

    first = _lark_staging_path(shared)
    second = _lark_staging_path(shared)

    assert first != second
    assert first.parent == shared.parent
    assert first.name.endswith(".tmp")


def test_the_cache_header_covers_start_and_position_mode() -> None:
    base = _lark_cache_header(start="start", propagate_positions=True)

    assert base.startswith(b"SATTLINE-LARK-CACHE-V1 ")
    assert base.endswith(b"\n")
    assert _lark_cache_header(start="start", propagate_positions=False) != base
    assert _lark_cache_header(start="modulecode", propagate_positions=True) != base


def _patch_cache_path(monkeypatch: pytest.MonkeyPatch, cache_path: Path) -> None:
    def _path(*, start: str, propagate_positions: bool) -> str:
        del start, propagate_positions
        return str(cache_path)

    monkeypatch.setattr(source_io, "_parser_cache_path", _path)


def test_a_cold_build_publishes_the_cache_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "cache.lark"
    _patch_cache_path(monkeypatch, cache_path)
    published: list[tuple[object, object]] = []
    real_replace = os.replace

    def _replace(source: object, target: object, **kwargs: object) -> None:
        published.append((source, target))
        real_replace(source, target, **kwargs)  # type: ignore[arg-type]

    with patch(f"{source_io.__name__}.os.replace", side_effect=_replace):
        parser = build_lark_parser()

    assert parser is not None
    assert cache_path.is_file()
    assert cache_path.read_bytes().startswith(b"SATTLINE-LARK-CACHE-V1 ")
    assert len(published) == 1
    staging, target = published[0]
    assert Path(str(staging)).parent == cache_path.parent
    assert Path(str(target)) == cache_path
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_warm_build_reads_the_cache_without_rewriting_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "cache.lark"
    _patch_cache_path(monkeypatch, cache_path)
    build_lark_parser()
    before = cache_path.stat()

    build_lark_parser()

    after = cache_path.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_truncated_cache_file_is_discarded_and_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The truncation recovery stays, and the repair is one atomic replace."""
    cache_path = tmp_path / "cache.lark"
    cache_path.write_bytes(b"truncated")
    _patch_cache_path(monkeypatch, cache_path)

    build_lark_parser()

    repaired = cache_path.read_bytes()
    assert repaired.startswith(b"SATTLINE-LARK-CACHE-V1 ")
    assert len(repaired) > len(b"truncated")
    assert list(tmp_path.glob("*.tmp")) == []
    # The repaired file is a usable cache: a second build keeps its identity.
    before = cache_path.stat()
    build_lark_parser()
    after = cache_path.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_a_partial_cache_body_is_discarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A killed writer's half-written pickle is a cold cache, never a crash."""
    cache_path = tmp_path / "cache.lark"
    cache_path.write_bytes(_lark_cache_header(start="start", propagate_positions=True) + b"\x80\x05trunc")
    _patch_cache_path(monkeypatch, cache_path)

    parser = build_lark_parser()

    assert parser is not None
    assert cache_path.stat().st_size > len(b"\x80\x05trunc")
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_file_from_an_older_format_is_discarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "cache.lark"
    cache_path.write_bytes(b"an older cache format\n" + b"payload")
    _patch_cache_path(monkeypatch, cache_path)

    build_lark_parser()

    assert cache_path.read_bytes().startswith(b"SATTLINE-LARK-CACHE-V1 ")


def test_a_failed_publish_leaves_a_cold_cache_not_a_failed_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "cache.lark"
    _patch_cache_path(monkeypatch, cache_path)

    with patch(f"{source_io.__name__}.os.replace", side_effect=OSError("disk full")):
        parser = build_lark_parser()

    assert parser is not None
    assert not cache_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_failed_serialize_leaves_no_cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "cache.lark"
    _patch_cache_path(monkeypatch, cache_path)

    with patch("lark.Lark.save", side_effect=ValueError("cannot serialize")):
        parser = build_lark_parser()

    assert parser is not None
    assert not cache_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_cache_hit_produces_the_same_ast_as_a_fresh_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The saved parser restores the contextual lexer, so the AST is identical."""
    cache_path = tmp_path / "cache.lark"
    _patch_cache_path(monkeypatch, cache_path)
    fresh = build_lark_parser()
    cached = build_lark_parser()
    source = (
        Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "valid" / "GraphObjectGeometry.s"
    ).read_bytes()
    source_text = source.decode("cp1252")

    assert fresh is not cached
    assert parse_source_text(source_text, parser=fresh) == parse_source_text(source_text, parser=cached)


def test_a_missing_cache_path_builds_without_a_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_cache(*, start: str, propagate_positions: bool) -> None:
        del start, propagate_positions
        return None

    monkeypatch.setattr(source_io, "_parser_cache_path", _no_cache)

    with patch.object(source_io, "_build_cached_lark_parser", side_effect=AssertionError("must not cache")):
        parser = build_lark_parser()

    assert parser is not None
