"""Parser-owned file-lookup cache.

Persists ``(kind, name, mode) -> (base_dir, ext)`` resolutions so consecutive
project loads skip filesystem scans for stable layouts. This is the parser's own
on-disk namespace and version — independent of any consumer-tooling cache
identifiers (Q7, plan §6) — and SattLint stops reading it once the adapter lands.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

LOOKUP_CACHE_VERSION = 1

DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL = 25


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
        except (OSError, json.JSONDecodeError):
            return
        data = _as_data_dict(payload)
        if data is None or data.get("version") != LOOKUP_CACHE_VERSION:
            return
        entries = _load_file_lookup_entries(data.get("entries"))
        if entries is not None:
            self._data = {"version": LOOKUP_CACHE_VERSION, "entries": entries}

    def prune_stale_entries(self) -> int:
        if not self.path.exists():
            return 0
        try:
            payload = _read_json(self.path)
        except (OSError, json.JSONDecodeError):
            return 1 if _remove_file(self.path) else 0
        data = _as_data_dict(payload)
        if data is None or data.get("version") != LOOKUP_CACHE_VERSION:
            return 1 if _remove_file(self.path) else 0
        return 0

    def drain_startup_pruned_entries(self) -> int:
        removed = self._startup_pruned_entries
        self._startup_pruned_entries = 0
        return removed

    def _save(self) -> None:
        payload: dict[str, object] = {
            "version": LOOKUP_CACHE_VERSION,
            "entries": self._data.get("entries", {}),
        }
        temp_path = self.path.with_name(f"{self.path.name}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, self.path)

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
        self._save()
        self._dirty = False
        self._pending_mutations = 0


__all__ = [
    "DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL",
    "LOOKUP_CACHE_VERSION",
    "FileLookupCache",
]
