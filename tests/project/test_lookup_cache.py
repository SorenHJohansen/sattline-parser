# pyright: reportPrivateUsage=false
"""Unit tests for the parser-owned ``project/lookup_cache.py``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.project.lookup_cache import (
    DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL,
    LOOKUP_CACHE_VERSION,
    FileLookupCache,
    _as_file_lookup_entry,
    _load_file_lookup_entries,
    _normalize_base_dir,
    _remove_file,
)

_CACHE_PATH = "sattline_parser.project.lookup_cache"


def _write_raw(cache_dir: Path, payload: object) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "file_lookup_cache.json").write_text(json.dumps(payload), encoding="utf-8")


def test_defaults_are_exposed() -> None:
    assert DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL == 25
    assert isinstance(LOOKUP_CACHE_VERSION, int)


def test_set_get_roundtrip_casefolds_name(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path, write_through=True)
    base_dir = Path("/tmp/X")
    cache.set("code", "ControlLib", "draft", base_dir=base_dir, ext=".s")
    assert cache.get("code", "controllib", "draft") == {
        "base_dir": _normalize_base_dir(base_dir),
        "ext": ".s",
    }
    assert cache.get("code", "Unknown", "draft") is None


def test_set_get_roundtrips_resolved_base_dir(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    cache = FileLookupCache(tmp_path, write_through=True)
    cache.set("deps", "Lib", "official", base_dir=base, ext=".z")
    entry = cache.get("deps", "lib", "official")
    assert entry is not None
    assert entry["base_dir"] == str(base.resolve())


def test_set_identical_entry_is_not_mutating(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path, flush_interval=None)
    cache.set("code", "A", "draft", base_dir=Path("/x"), ext=".s")
    assert cache._pending_mutations == 1
    cache.set("code", "A", "draft", base_dir=Path("/x"), ext=".s")
    assert cache._pending_mutations == 1


def test_forget_removes_entry(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path, write_through=True)
    cache.set("code", "A", "draft", base_dir=Path("/x"), ext=".s")
    cache.forget("code", "A", "draft")
    assert cache.get("code", "A", "draft") is None
    cache.forget("code", "A", "draft")


def test_write_through_persists_and_reloads(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path, write_through=True)
    base_dir = Path("/data/lib")
    cache.set("code", "Lib", "official", base_dir=base_dir, ext=".x")
    reloaded = FileLookupCache(tmp_path, write_through=True)
    assert reloaded.get("code", "lib", "official") == {
        "base_dir": _normalize_base_dir(base_dir),
        "ext": ".x",
    }


def test_flush_interval_skips_disk_until_threshold(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path, flush_interval=2)
    cache.set("code", "A", "draft", base_dir=Path("/x"), ext=".s")
    assert not (tmp_path / "file_lookup_cache.json").exists()
    cache.set("deps", "A", "draft", base_dir=Path("/x"), ext=".l")
    assert (tmp_path / "file_lookup_cache.json").exists()


def test_flush_noop_when_clean(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path)
    cache.flush()
    assert not (tmp_path / "file_lookup_cache.json").exists()


def test_invalid_flush_interval_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="flush_interval"):
        FileLookupCache(tmp_path, flush_interval=0)


def test_prunes_wrong_version_at_startup(tmp_path: Path) -> None:
    _write_raw(tmp_path, {"version": LOOKUP_CACHE_VERSION + 1, "entries": {}})
    cache = FileLookupCache(tmp_path)
    assert cache.drain_startup_pruned_entries() == 1
    assert cache.get("code", "A", "draft") is None


def test_prunes_corrupted_json_at_startup(tmp_path: Path) -> None:
    (tmp_path / "file_lookup_cache.json").write_text("{not json", encoding="utf-8")
    cache = FileLookupCache(tmp_path)
    assert cache.drain_startup_pruned_entries() == 1
    assert not (tmp_path / "file_lookup_cache.json").exists()


def test_load_ignores_corrupt_or_wrong_version_json_direct(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path)
    (tmp_path / "file_lookup_cache.json").write_text("{bad", encoding="utf-8")
    cache._load()
    assert cache.get("code", "A", "draft") is None
    _write_raw(tmp_path, [1, 2, 3])
    cache._load()
    assert cache.get("code", "A", "draft") is None
    _write_raw(
        tmp_path, {"version": LOOKUP_CACHE_VERSION + 1, "entries": {"code:draft:A": {"base_dir": "/x", "ext": ".s"}}}
    )
    cache._load()
    assert cache.get("code", "A", "draft") is None


def test_ignores_unparseable_entries_on_load(tmp_path: Path) -> None:
    _write_raw(tmp_path, {"version": LOOKUP_CACHE_VERSION, "entries": {"code:draft:A": "bad"}})
    cache = FileLookupCache(tmp_path, write_through=True)
    assert cache.get("code", "A", "draft") is None


def test_set_guards_against_non_dict_entries(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path)
    cache._data = {"version": LOOKUP_CACHE_VERSION, "entries": 42}
    cache.set("code", "A", "draft", base_dir=Path("/x"), ext=".s")
    cache.forget("code", "A", "draft")
    assert cache.get("code", "A", "draft") is None


def test_normalize_base_dir_resolves(tmp_path: Path) -> None:
    base = tmp_path / "sub"
    base.mkdir()
    assert _normalize_base_dir(base) == str(base.resolve())


def test_normalize_base_dir_falls_back_on_resolve_error(tmp_path: Path) -> None:
    with patch(f"{_CACHE_PATH}.Path.resolve", side_effect=OSError("boom")):
        assert _normalize_base_dir(Path("~")) == str(Path("~").expanduser())


def test_as_file_lookup_entry_shapes() -> None:
    assert _as_file_lookup_entry({"base_dir": "/x", "ext": ".s"}) == {"base_dir": "/x", "ext": ".s"}
    assert _as_file_lookup_entry(None) is None
    assert _as_file_lookup_entry({"base_dir": "/x"}) is None
    assert _as_file_lookup_entry({"base_dir": 1, "ext": ".s"}) is None


def test_load_file_lookup_entries_shapes() -> None:
    assert _load_file_lookup_entries({"code:draft:A": {"base_dir": "/x", "ext": ".s"}}) == {
        "code:draft:A": {"base_dir": "/x", "ext": ".s"}
    }
    assert _load_file_lookup_entries(None) is None
    assert _load_file_lookup_entries({"code:draft:A": {}}) is None
    assert _load_file_lookup_entries({1: {"base_dir": "/x", "ext": ".s"}}) is None


def test_remove_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert not _remove_file(missing)
    present = tmp_path / "x"
    present.write_text("x", encoding="utf-8")
    assert _remove_file(present)
    assert not present.exists()
    (tmp_path / "locked").write_text("x", encoding="utf-8")
    with patch(f"{_CACHE_PATH}.Path.unlink", side_effect=OSError("boom")):
        assert not _remove_file(tmp_path / "locked")
