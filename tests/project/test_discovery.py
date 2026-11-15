# pyright: reportPrivateUsage=false
"""Unit tests for file discovery (``project/discovery.py``)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import pytest

from sattline_parser.project import (
    ArtifactKind,
    FileLookupCache,
    LoadMode,
    ProjectLoadError,
    ProjectLookup,
    SourceIndex,
    ordered_lookup_bases,
    parse_search_path,
)
from sattline_parser.project.discovery import (
    _is_allowed_base,
    _is_relative_to,
    _is_safe_name,
    _resolved,
)

from ._support import write_file

_DISCOVERY_PATH = "sattline_parser.project.discovery"


def test_resolved_paths() -> None:
    assert _resolved(None) is None
    resolved = _resolved(Path("."))
    assert resolved is not None and resolved.is_absolute()
    with patch(f"{_DISCOVERY_PATH}.Path.resolve", side_effect=OSError("boom")):
        assert _resolved(Path("/x")) == Path("/x")


def test_is_relative_to_edges(tmp_path: Path) -> None:
    root = tmp_path / "a"
    child = root / "b"
    assert _is_relative_to(child, root)
    assert not _is_relative_to(root, child)
    assert not _is_relative_to(None, root)
    assert not _is_relative_to(child, None)


def test_is_allowed_base(tmp_path: Path) -> None:
    root_a = write_file(tmp_path, "a/.keep")
    root_b = write_file(tmp_path, "b/.keep")
    assert _is_allowed_base([root_a, root_b], root_a)
    assert not _is_allowed_base([root_a], tmp_path / "elsewhere")


def test_source_index_builds_and_finds(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "Alpha.s")
    write_file(root, "Beta.x")
    write_file(root, "Gamma.l")
    write_file(root, "Delta.z")
    write_file(root, "Epsilon.g")
    write_file(root, "Nested/Eta.s")

    index = SourceIndex([root])
    assert index.roots == (root,)
    assert index.find_in_index(base=root, name="alpha", extensions=(".s", ".x")) == root / "Alpha.s"
    assert index.find_in_index(base=root, name="Beta", extensions=(".s", ".x")) == root / "Beta.x"
    assert index.find_in_index(base=root, name="Gamma", extensions=(".l", ".z")) == root / "Gamma.l"
    assert index.find_in_index(base=root, name="Delta", extensions=(".z",)) == root / "Delta.z"
    assert index.find_in_index(base=root, name="Epsilon", extensions=(".g", ".y")) is None
    assert index.find_in_index(base=root, name="Alpha", extensions=(".x",)) is None
    assert index.find_in_index(base=root, name="Missing", extensions=(".s",)) is None
    assert index.find_in_index(base=root / "unknown", name="Alpha", extensions=(".s",)) is None
    assert index.find_in_index(base=tmp_path / "nodir", name="Alpha", extensions=(".s",)) is None


def test_source_index_add_registers_after_index_build(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    index = SourceIndex([root])
    # Build the cache while the directory is empty; the late file must not appear.
    assert index.find_in_index(base=root, name="Absent", extensions=(".s",)) is None
    late = write_file(root, "Late.s")
    assert index.find_in_index(base=root, name="Late", extensions=(".s",)) is None
    index.add(base=root, name="Late", path=late)
    assert index.find_in_index(base=root, name="late", extensions=(".s",)) == late


def test_source_index_rejects_missing_and_file_bases(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    index = SourceIndex([root])
    assert index.find_in_index(base=root / "missing", name="X", extensions=(".s",)) is None
    a_file = write_file(tmp_path, "f.s")
    assert index.find_in_index(base=a_file, name="f", extensions=(".s",)) is None


def test_ordered_lookup_bases_keeps_the_caller_order(tmp_path: Path) -> None:
    first = write_file(tmp_path, "first/.keep")
    second = write_file(tmp_path, "second/.keep")
    third = write_file(tmp_path, "third/.keep")

    assert ordered_lookup_bases([first, second, third]) == (
        first.resolve(),
        second.resolve(),
        third.resolve(),
    )
    assert ordered_lookup_bases([third, first, second]) == (
        third.resolve(),
        first.resolve(),
        second.resolve(),
    )


def test_ordered_lookup_bases_drops_duplicates_keeping_the_first_position(tmp_path: Path) -> None:
    first = write_file(tmp_path, "first/.keep")
    second = write_file(tmp_path, "second/.keep")

    assert ordered_lookup_bases([first, second, first]) == (first.resolve(), second.resolve())


def test_ordered_lookup_bases_empty() -> None:
    assert ordered_lookup_bases([]) == ()


def test_ordered_lookup_bases_keeps_case_distinct_roots_on_a_case_sensitive_filesystem(tmp_path: Path) -> None:
    upper = tmp_path / "Library"
    lower = tmp_path / "library"
    upper.mkdir()
    lower.mkdir()
    if upper.resolve() == lower.resolve():
        pytest.skip("filesystem is case-insensitive")

    ordered = ordered_lookup_bases([upper, lower])

    assert ordered == (upper.resolve(), lower.resolve())


def test_parse_search_path_accepts_backslashes_and_whitespace(tmp_path: Path) -> None:
    base = tmp_path / "sattline"

    roots = parse_search_path(r" LibA\UnitLib , LibB/UnitLib ,, ", base=base)

    assert roots == ((base / "LibA/UnitLib").resolve(), (base / "LibB/UnitLib").resolve())


def test_parse_search_path_resolves_relative_entries_under_a_base(tmp_path: Path) -> None:
    base = tmp_path / "sattline"
    absolute = tmp_path / "elsewhere" / "Lib"

    roots = parse_search_path(f"LibA/UnitLib,{absolute}", base=base)

    assert roots == ((base / "LibA/UnitLib").resolve(), absolute.resolve())


@pytest.mark.skipif(os.name == "nt", reason="the POSIX rule is for non-Windows hosts")
@pytest.mark.parametrize("entry", [r"C:\SattLine\Lib", r"\\server\share\Lib"])
def test_parse_search_path_rejects_a_windows_absolute_entry_on_posix(entry: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Windows path"):
        parse_search_path(entry, base=tmp_path)


def test_parse_search_path_drops_duplicates_and_rejects_an_empty_path(tmp_path: Path) -> None:
    base = tmp_path / "sattline"

    assert parse_search_path(r"LibA\UnitLib,LibA/UnitLib", base=base) == ((base / "LibA/UnitLib").resolve(),)
    with pytest.raises(ValueError, match="no entries"):
        parse_search_path(" , ,, ", base=base)


def test_lookup_path_order_wins_over_a_later_root(tmp_path: Path) -> None:
    """Program1 in LibA and in LibB resolves to LibA; the LibB body never wins."""
    gc = tmp_path / "LibA" / "UnitLib"
    ha = tmp_path / "LibB" / "UnitLib"
    write_file(gc, "Program1.s")
    write_file(ha, "Program1.s")

    lookup = ProjectLookup([gc, ha], LoadMode.DRAFT)

    assert lookup.find_code("Program1") == gc / "Program1.s"


def test_lookup_path_order_wins_in_both_directions(tmp_path: Path) -> None:
    gc = tmp_path / "LibA" / "UnitLib"
    ha = tmp_path / "LibB" / "UnitLib"
    write_file(gc, "Program1.s")
    write_file(ha, "Program1.s")

    assert ProjectLookup([gc, ha], LoadMode.DRAFT).find_code("Program1") == gc / "Program1.s"
    assert ProjectLookup([ha, gc], LoadMode.DRAFT).find_code("Program1") == ha / "Program1.s"


def test_a_requester_inside_a_later_root_does_not_override_the_path_order(tmp_path: Path) -> None:
    gc = tmp_path / "LibA" / "UnitLib"
    ha = tmp_path / "LibB" / "UnitLib"
    write_file(gc, "Dep.s")
    write_file(ha, "Dep.s")

    # LibB is the second entry, so its body is the requester's own root; the path
    # order still decides, and LibA is scanned first.
    lookup = ProjectLookup([gc, ha], LoadMode.DRAFT)

    assert lookup.find_code("Dep") == gc / "Dep.s"


def test_lookup_draft_prefers_s_then_falls_back_to_x(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "A.s")
    write_file(root, "B.x")
    lookup = ProjectLookup([root], LoadMode.DRAFT)
    assert lookup.find_code("A") == root / "A.s"
    assert lookup.find_code("b") == root / "B.x"


def test_lookup_draft_deps_prefers_l_then_z(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "C.l")
    write_file(root, "D.z")
    lookup = ProjectLookup([root], LoadMode.DRAFT)
    assert lookup.find_deps("C") == root / "C.l"
    assert lookup.find_deps("D") == root / "D.z"


def test_lookup_official_accepts_only_official_extensions(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "A.s")
    write_file(root, "E.x")
    lookup = ProjectLookup([root], LoadMode.OFFICIAL)
    assert lookup.find_code("A") is None
    assert lookup.find_code("E") == root / "E.x"


def test_lookup_root_precedence_prefers_earlier_root(tmp_path: Path) -> None:
    root_a = tmp_path / "ra"
    root_a.mkdir()
    root_b = tmp_path / "rb"
    root_b.mkdir()
    write_file(root_a, "A.s")
    write_file(root_b, "A.s")
    write_file(root_b, "A.x")
    lookup = ProjectLookup([root_a, root_b], LoadMode.DRAFT)
    assert lookup.find_code("A") == root_a / "A.s"


def test_lookup_missing_reports_via_debug(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    messages: list[str] = []
    lookup = ProjectLookup([root], LoadMode.OFFICIAL, debug=messages.append)
    assert lookup.find_code("Missing") is None
    assert any("No code file found" in message for message in messages)


def test_lookup_refuses_root_ordered_companion_search(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "Pic.g")
    write_file(root, "Pic.q")
    lookup = ProjectLookup([root], LoadMode.DRAFT)
    for kind in (ArtifactKind.GRAPHICS, ArtifactKind.DISTRIBUTION):
        with pytest.raises(ValueError, match="beside the body"):
            lookup.find("Pic", kind)


def test_companions_never_enter_the_source_index(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "Pic.g")
    write_file(root, "Pic.q")
    index = SourceIndex([root])
    lookup = ProjectLookup([root], LoadMode.DRAFT, index=index)
    with pytest.raises(ValueError):
        lookup.find("Pic", ArtifactKind.GRAPHICS)
    assert index.find_in_index(base=root, name="Pic", extensions=(".g",)) is None
    assert index.find_in_index(base=root, name="Pic", extensions=(".q",)) is None


def test_lookup_custom_index_discovers_previously_unindexed_file(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    index = SourceIndex([root])
    lookup = ProjectLookup([root], LoadMode.DRAFT, index=index)
    write_file(root, "NewFile.s")
    found = lookup.find_code("NewFile")
    assert found == root / "NewFile.s"
    assert index.find_in_index(base=root, name="NewFile", extensions=(".s",)) == found


def test_lookup_uses_and_validates_cached_base(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "A.s")
    cache_dir = tmp_path / "cache"
    cache = FileLookupCache(cache_dir, write_through=True)
    lookup = ProjectLookup([root], LoadMode.DRAFT, cache=cache)
    assert lookup.find_code("A") == root / "A.s"
    assert cache.get("code", "a", LoadMode.DRAFT.value) == {"base_dir": str(root.resolve()), "ext": ".s"}
    assert lookup.find_deps("A") is None


def test_find_in_cached_base_direct(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "Cached.x")
    cache_dir = tmp_path / "cache"
    cache = FileLookupCache(cache_dir, write_through=True)
    lookup = ProjectLookup([root], LoadMode.OFFICIAL, cache=cache)
    ordered = ordered_lookup_bases([root])

    plain = ProjectLookup([root], LoadMode.OFFICIAL)
    assert plain._find_in_cached_base("code", "Cached", (".x",), ordered=ordered) is None

    cache.set("code", "Cached", LoadMode.OFFICIAL.value, root, ".x")
    assert lookup._find_in_cached_base("code", "Cached", (".x",), ordered=ordered) == (root / "Cached.x", root)

    cache.set("code", "Cached", LoadMode.OFFICIAL.value, root, ".y")
    hit_stale = lookup._find_in_cached_base("code", "Cached", (".x",), ordered=ordered)
    assert hit_stale == (root / "Cached.x", root)

    cache.set("code", "Other", LoadMode.OFFICIAL.value, root, ".z")
    assert cache.get("code", "Other", LoadMode.OFFICIAL.value) is not None
    assert lookup._find_in_cached_base("code", "Other", (".x",), ordered=ordered) is None
    assert cache.get("code", "Other", LoadMode.OFFICIAL.value) is None

    cache.set("code", "Gone", LoadMode.OFFICIAL.value, root, ".s")
    assert lookup._find_in_cached_base("code", "Gone", (".s",), ordered=ordered) is None

    outside = tmp_path / "outside"
    cache.set("code", "Fake", LoadMode.OFFICIAL.value, outside, ".x")
    assert lookup._find_in_cached_base("code", "Fake", (".x",), ordered=ordered) is None
    assert cache.get("code", "Fake", LoadMode.OFFICIAL.value) is None

    cache.set("code", "Empty", LoadMode.OFFICIAL.value, Path(""), ".x")
    assert lookup._find_in_cached_base("code", "Empty", (".x",), ordered=ordered) is None


def test_find_in_cached_base_rejects_base_outside_ordering(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "X.x")
    cache_dir = tmp_path / "cache"
    cache = FileLookupCache(cache_dir, write_through=True)
    lookup = ProjectLookup([root], LoadMode.OFFICIAL, cache=cache)
    cache.set("code", "X", LoadMode.OFFICIAL.value, root, ".x")
    assert lookup._find_in_cached_base("code", "X", (".x",), ordered=()) is None
    assert cache.get("code", "X", LoadMode.OFFICIAL.value) is None


def test_find_in_cached_base_prefers_outranking_base(tmp_path: Path) -> None:
    requester = tmp_path / "cluster" / "programs"
    requester.mkdir(parents=True)
    dep_root = tmp_path / "cluster" / "libs"
    dep_root.mkdir(parents=True)
    write_file(requester, "A.x")
    write_file(dep_root, "A.x")
    cache_dir = tmp_path / "cache"
    cache = FileLookupCache(cache_dir, write_through=True)
    lookup = ProjectLookup([requester, dep_root], LoadMode.OFFICIAL, cache=cache)
    ordered = ordered_lookup_bases([requester, dep_root])
    assert ordered[0] == requester.resolve()
    cache.set("code", "A", LoadMode.OFFICIAL.value, dep_root, ".x")
    assert lookup._find_in_cached_base("code", "A", (".x",), ordered=ordered) == (requester / "A.x", requester)
    assert cache.get("code", "A", LoadMode.OFFICIAL.value) == {
        "base_dir": str(requester.resolve()),
        "ext": ".x",
    }


def test_find_in_cached_base_falls_through_to_cached_base(tmp_path: Path) -> None:
    requester = tmp_path / "cluster" / "programs"
    requester.mkdir(parents=True)
    dep_root = tmp_path / "cluster" / "libs"
    dep_root.mkdir(parents=True)
    write_file(dep_root, "B.x")
    cache_dir = tmp_path / "cache"
    cache = FileLookupCache(cache_dir, write_through=True)
    lookup = ProjectLookup([requester, dep_root], LoadMode.OFFICIAL, cache=cache)
    ordered = ordered_lookup_bases([requester, dep_root])
    cache.set("code", "B", LoadMode.OFFICIAL.value, dep_root, ".x")
    assert lookup._find_in_cached_base("code", "B", (".x",), ordered=ordered) == (dep_root / "B.x", dep_root)


def _raise_if_called(
    self: ProjectLookup,
    name: str,
    extensions: Sequence[str],
    base: Path,
    *,
    kind: str,
) -> Path:
    raise AssertionError("cached resolution must not rescan")


def test_find_returns_cached_result_without_scanning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "p"
    write_file(root, "Cached.s")
    cache_dir = tmp_path / "cache"
    cache = FileLookupCache(cache_dir, write_through=True)
    first = ProjectLookup([root], LoadMode.DRAFT, cache=cache)
    assert first.find_code("Cached") == root / "Cached.s"

    fresh = ProjectLookup([root], LoadMode.DRAFT, cache=cache)
    monkeypatch.setattr(ProjectLookup, "_find_in_base", _raise_if_called)
    assert fresh.find_code("Cached") == root / "Cached.s"


def test_find_full_scan_fallbacks(tmp_path: Path) -> None:
    root = tmp_path / "p"
    write_file(root, "A.s")
    write_file(root, "Z.x")

    lookup = ProjectLookup([root], LoadMode.DRAFT)
    assert lookup.find_code("A") == root / "A.s"

    indexed = ProjectLookup([root], LoadMode.DRAFT)
    assert indexed.find_code("Z") == root / "Z.x"

    missing = ProjectLookup([root], LoadMode.DRAFT)
    assert missing.find_code("Nope") is None

    late = ProjectLookup([root], LoadMode.DRAFT)
    # Build the index before the file exists, so resolution has to fall back to a scan.
    assert late._index.find_in_index(base=root, name="Absent", extensions=(".s",)) is None
    late_file = write_file(root, "Late.s")
    assert late.find_code("Late") == late_file
    assert late._index.find_in_index(base=root, name="Late", extensions=(".s",)) == late_file


def test_find_forgets_cached_entry_when_file_is_gone(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    cache = FileLookupCache(tmp_path / "cache", write_through=True)
    lookup = ProjectLookup([root], LoadMode.OFFICIAL, cache=cache)
    cache.set("code", "Keep", LoadMode.OFFICIAL.value, root, ".x")
    assert lookup.find("Keep", ArtifactKind.CODE) is None
    assert cache.get("code", "Keep", LoadMode.OFFICIAL.value) is None


def test_find_cache_refreshes_when_higher_precedence_file_appears(tmp_path: Path) -> None:
    requester = tmp_path / "cluster" / "programs"
    requester.mkdir(parents=True)
    dep_root = tmp_path / "cluster" / "libs"
    dep_root.mkdir(parents=True)
    write_file(dep_root, "A.s")
    cache_dir = tmp_path / "cache"
    cache = FileLookupCache(cache_dir, write_through=True)
    first = ProjectLookup([requester, dep_root], LoadMode.DRAFT, cache=cache)
    assert first.find_code("A") == dep_root / "A.s"

    write_file(requester, "A.s")
    second = ProjectLookup([requester, dep_root], LoadMode.DRAFT, cache=cache)
    assert second.find_code("A") == requester / "A.s"
    assert cache.get("code", "a", LoadMode.DRAFT.value) == {
        "base_dir": str(requester.resolve()),
        "ext": ".s",
    }


def test_lookup_refuses_a_dependency_name_with_a_parent_reference(tmp_path: Path) -> None:
    """A dependency name is a unit name, never a path into another tree."""
    root = tmp_path / "lib"
    root.mkdir()
    write_file(tmp_path, "outside/Secret.s")

    lookup = ProjectLookup([root], LoadMode.DRAFT)

    assert lookup.find_code("../outside/Secret") is None


def test_lookup_refuses_an_absolute_dependency_name(tmp_path: Path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    outside = write_file(tmp_path, "outside/Secret.s")

    lookup = ProjectLookup([root], LoadMode.DRAFT)

    assert lookup.find_code(str(outside)) is None


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("Main", True),
        ("Main_2", True),
        ("A" * 20, True),
        ("A" * 21, False),
        ("", False),
        ("../outside/Secret", False),
        ("..\\outside\\Secret", False),
        ("D:ExternalProgram", False),
        ("\\\\server\\share\\Prog", False),
        ("Main.s", False),
        ("Name ", False),
        ("Name.", False),
    ],
)
def test_unit_names_are_validated_as_sattline_identifiers(name: str, safe: bool) -> None:
    assert _is_safe_name(name) is safe


@pytest.mark.parametrize("name", ["CON", "prn", "COM1", "lpt9"])
def test_windows_reserved_device_names_are_safe_on_posix(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sattline_parser.project.discovery._IS_WINDOWS", False)

    assert _is_safe_name(name) is True


@pytest.mark.parametrize("name", ["CON", "prn", "COM1", "lpt9"])
def test_windows_reserved_device_names_are_refused_only_on_windows(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sattline_parser.project.discovery._IS_WINDOWS", True)

    assert _is_safe_name(name) is False


def test_find_deps_beside_refuses_a_name_with_a_path(tmp_path: Path) -> None:
    root = tmp_path / "lib"
    root.mkdir()
    body = write_file(root, "Main.s")
    write_file(tmp_path, "outside/Secret.l", "Lib\n")

    lookup = ProjectLookup([root], LoadMode.DRAFT)

    assert lookup.find_deps_beside(body, "../outside/Secret") is None
    assert lookup.find_deps_beside(body, str(tmp_path / "outside" / "Secret")) is None


def test_find_in_base_requires_containment_for_the_stat_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stat fallback builds a path from the name, so it checks containment too."""
    root = tmp_path / "lib"
    root.mkdir()
    write_file(tmp_path, "outside/Secret.s")

    # Bypass the name guard so the containment check is the only barrier left.
    def always_safe(name: str) -> bool:
        del name
        return True

    monkeypatch.setattr(f"{_DISCOVERY_PATH}._is_safe_name", always_safe)

    lookup = ProjectLookup([root], LoadMode.DRAFT)

    assert lookup.find_code("../outside/Secret") is None
    assert lookup.find_code(str(tmp_path / "outside" / "Secret")) is None


def test_lookup_restats_an_index_hit_and_misses_a_deleted_body(tmp_path: Path) -> None:
    """A body deleted after the index was built must not resolve."""
    root = tmp_path / "lib"
    body = write_file(root, "Gone.s")
    lookup = ProjectLookup([root], LoadMode.DRAFT)

    assert lookup.find_code("Gone") == body
    body.unlink()

    assert lookup.find_code("Gone") is None


def test_lookup_restats_an_index_hit_for_a_sidecar(tmp_path: Path) -> None:
    root = tmp_path / "lib"
    body = write_file(root, "Main.s")
    sidecar = write_file(root, "Main.l", "Lib\n")
    lookup = ProjectLookup([root], LoadMode.DRAFT)

    assert lookup.find_deps_beside(body, "Main") == sidecar
    sidecar.unlink()

    assert lookup.find_deps_beside(body, "Main") is None


def test_an_unreadable_root_is_a_load_error(tmp_path: Path) -> None:
    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("mode bits deny reads on POSIX, and root bypasses them")
    root = tmp_path / "closed"
    root.mkdir()
    root.chmod(0o000)
    try:
        with pytest.raises(ProjectLoadError, match="cannot read"):
            SourceIndex([root]).find_in_index(base=root, name="Main", extensions=[".s"])
    finally:
        root.chmod(0o755)


def test_warm_cache_preserves_cold_extension_precedence(tmp_path: Path) -> None:
    """A warm lookup must not shadow a preferred extension that appeared later.

    The cache recorded ``.x`` for this prefix; a ``.s`` then appeared. Draft
    mode prefers ``.s``, so warm and cold lookups must agree.
    """
    root = tmp_path / "p"
    cache_dir = tmp_path / "cache"
    write_file(root, "Lib.x")

    cache = FileLookupCache(cache_dir)
    cold_first = ProjectLookup([root], LoadMode.DRAFT, cache=cache).find_code("Lib")
    assert cold_first == root / "Lib.x"
    cache.flush()

    write_file(root, "Lib.s")

    warm = ProjectLookup([root], LoadMode.DRAFT, cache=FileLookupCache(cache_dir)).find_code("Lib")
    cold = ProjectLookup([root], LoadMode.DRAFT).find_code("Lib")
    assert warm == cold == root / "Lib.s"


def test_warm_cache_resolves_a_name_whose_case_differs(tmp_path: Path) -> None:
    """A cold lookup is case-insensitive; the warm path must not lose that."""
    root = tmp_path / "p"
    cache_dir = tmp_path / "cache"
    write_file(root, "Mixed.s")
    write_file(root, "mixed.x")

    first = FileLookupCache(cache_dir)
    assert ProjectLookup([root], LoadMode.DRAFT, cache=first).find_code("mixed") == root / "Mixed.s"
    first.flush()

    warm = ProjectLookup([root], LoadMode.DRAFT, cache=FileLookupCache(cache_dir))
    cold = ProjectLookup([root], LoadMode.DRAFT)

    assert warm.find_code("mixed") == cold.find_code("mixed") == root / "Mixed.s"
