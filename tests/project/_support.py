"""Shared helpers for the project-layer tests."""

from __future__ import annotations

from pathlib import Path


def write_file(root: Path, rel: str, content: str = "") -> Path:
    """Write *content* to ``root / rel``, creating parent directories."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
