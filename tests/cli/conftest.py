"""Fixtures for ``sattline`` CLI tests.

The ``project`` command caches parsed ASTs in the user's cache directory by
default, so every CLI test runs against its own cache root.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_cache_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
