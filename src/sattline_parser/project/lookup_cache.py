"""Parser-owned file-lookup cache.

Persists ``(kind, name, mode) -> (base_dir, ext)`` resolutions so consecutive
project loads skip filesystem scans for stable layouts. The namespace and
version belong to this package. A resolution whose base directory is gone is
dropped at startup, abandoned temporary siblings are pruned, and the entry count
is capped so a long-lived cache directory stays bounded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from ._atomic import TEMP_SUFFIX, temp_file_is_abandoned
from ._atomic import temp_path_for as _temp_path_for

LOOKUP_CACHE_VERSION = 2

DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL = 25

#: The cache is an optimisation, not a store: past this many entries the surplus
#: is dropped in key order so a long-lived cache directory stays bounded.
MAX_LOOKUP_CACHE_ENTRIES = 512


def _normalize_base_dir(base_dir: Path) -> str:
    expanded = base_dir.expanduser()
    try:
        return str(expanded.resolve())
    except OSError:
        return str(expanded)


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _as_data_dict(value: object) -> dict[object, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[object, object], value)


def _as_file_lookup_entry(value: object) -> dict[str, str] | None:
    data = _as_data_dict(value)
    if data is None:
        return None
    base_dir = data.get("base_dir")
    ext = data.get("ext")
    if isinstance(base_dir, str) and isinstance(ext, str):
        return {"base_dir": base_dir, "ext": ext}
    return None


def _load_file_lookup_entries(value: object) -> dict[str, dict[str, str]] | None:
    data = _as_data_dict(value)
    if data is None:
        return None
    entries: dict[str, dict[str, str]] = {}
    for raw_key, raw_entry in data.items():
        if not isinstance(raw_key, str):
            return None
        entry = _as_file_lookup_entry(raw_entry)
        if entry is None:
            return None
        entries[raw_key] = entry
    return entries


def _remove_file(path: Path) -> bool:
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _base_dir_is_gone(entry: dict[str, str]) -> bool:
    """Whether the base directory a resolution was recorded against is gone."""
    try:
        return not Path(entry["base_dir"]).is_dir()
    except OSError:
        return True


class FileLookupCache:
    """File-lookup resolution cache with atomic, interval-flushed persistence."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        flush_interval: int | None = DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL,
        write_through: bool = False,
    ) -> None:
        if flush_interval is not None and flush_interval <= 0:
            raise ValueError("flush_interval must be positive or None")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.cache_dir / "file_lookup_cache.json"
        self._flush_interval = flush_interval
        self._write_through = write_through
        self._pending_mutations = 0
        self._data: dict[str, object] = {"version": LOOKUP_CACHE_VERSION, "entries": {}}
        self._dirty = False
        self._startup_pruned_entries = self.prune_stale_entries()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = _read_json(self.path)
        except (OSError, ValueError):
            # A truncated file, invalid JSON, or bytes that are not UTF-8 all
            # mean the same thing: this entry is unusable, so a later write
            # replaces it.
            return
        data = _as_data_dict(payload)
        if data is None or data.get("version") != LOOKUP_CACHE_VERSION:
            return
        entries = _load_file_lookup_entries(data.get("entries"))
        if entries is not None:
            self._data = {"version": LOOKUP_CACHE_VERSION, "entries": entries}

    def prune_stale_entries(self) -> int:
        """Drop unusable entries, abandoned temporary files, and surplus entries.

        Runs at construction, before the in-memory table is loaded, so the
        survivors are what a later ``_load`` sees. Returns the number of entries
        and files removed. An unusable cache file counts as one removal, because
        the whole file is discarded. A stale entry is one whose recorded base
        directory no longer exists, so it can never resolve again.
        """
        removed = self._prune_temporary_files()
        if not self.path.exists():
            return removed
        try:
            payload = _read_json(self.path)
        except (OSError, ValueError):
            return removed + (1 if _remove_file(self.path) else 0)
        data = _as_data_dict(payload)
        if data is None or data.get("version") != LOOKUP_CACHE_VERSION:
            return removed + (1 if _remove_file(self.path) else 0)
        entries = _load_file_lookup_entries(data.get("entries"))
        if entries is None:
            return removed + (1 if _remove_file(self.path) else 0)
        survivors = {key: entry for key, entry in entries.items() if not _base_dir_is_gone(entry)}
        surplus = len(survivors) - MAX_LOOKUP_CACHE_ENTRIES
        if surplus > 0:
            for key in sorted(survivors)[:surplus]:
                del survivors[key]
        dropped = len(entries) - len(survivors)
        if dropped:
            try:
                self._write_payload({"version": LOOKUP_CACHE_VERSION, "entries": survivors})
            except OSError:
                # The cache is an optimisation: a failed prune leaves the old
                # file in place, and the next successful flush replaces it.
                return removed
        return removed + dropped

    def _prune_temporary_files(self) -> int:
        if not self.cache_dir.exists():
            return 0
        removed = 0
        for path in self.cache_dir.iterdir():
            if not path.is_file() or not path.name.endswith(TEMP_SUFFIX):
                continue
            if temp_file_is_abandoned(path) and _remove_file(path):
                removed += 1
        return removed

    def drain_startup_pruned_entries(self) -> int:
        removed = self._startup_pruned_entries
        self._startup_pruned_entries = 0
        return removed

    def _write_payload(self, payload: dict[str, object]) -> None:
        temp_path = _temp_path_for(self.path)
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.path)
        except OSError:
            _remove_file(temp_path)
            raise

    def _save(self) -> None:
        self._write_payload({"version": LOOKUP_CACHE_VERSION, "entries": self._data.get("entries", {})})

    def _record_mutation(self) -> None:
        self._dirty = True
        self._pending_mutations += 1
        should_flush = self._write_through or (
            self._flush_interval is not None and self._pending_mutations >= self._flush_interval
        )
        if should_flush:
            self.flush()

    def _key(self, kind: str, name: str, mode: str) -> str:
        return f"{kind}:{mode}:{name.casefold()}"

    def _entries_map(self) -> dict[object, object] | None:
        entries = self._data.get("entries")
        if not isinstance(entries, dict):
            return None
        return cast(dict[object, object], entries)

    def get(self, kind: str, name: str, mode: str) -> dict[str, str] | None:
        entries = self._entries_map()
        if entries is None:
            return None
        return _as_file_lookup_entry(entries.get(self._key(kind, name, mode)))

    def set(self, kind: str, name: str, mode: str, base_dir: Path, ext: str) -> None:
        entries = self._entries_map()
        if entries is None:
            return
        payload: dict[str, str] = {"base_dir": _normalize_base_dir(base_dir), "ext": ext}
        if entries.get(self._key(kind, name, mode)) == payload:
            return
        entries[self._key(kind, name, mode)] = payload
        self._record_mutation()

    def forget(self, kind: str, name: str, mode: str) -> None:
        key = self._key(kind, name, mode)
        entries = self._entries_map()
        if entries is None:
            return
        if key in entries:
            entries.pop(key, None)
            self._record_mutation()

    def flush(self) -> None:
        if not self._dirty:
            return
        try:
            self._save()
        except OSError:
            # The cache is an optimisation: keep the data in memory and retry on
            # the next flush rather than failing the load that triggered it.
            return
        self._dirty = False
        self._pending_mutations = 0


__all__ = [
    "DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL",
    "LOOKUP_CACHE_VERSION",
    "MAX_LOOKUP_CACHE_ENTRIES",
    "FileLookupCache",
]
