"""Shared pytest fixtures and test utilities."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sattline_parser.api import create_parser  # noqa: E402
from sattline_parser.transformer.sl_transformer import SLTransformer  # noqa: E402


@pytest.fixture
def case_sensitive_fs(tmp_path: Path) -> None:
    """Require a filesystem that can represent case-only distinct names."""
    probe = tmp_path / "case-probe"
    probe.touch()
    if (tmp_path / "CASE-PROBE").exists():
        pytest.skip("filesystem does not distinguish case-only names")
    probe.unlink()


@pytest.fixture
def symlink_supported(tmp_path: Path) -> None:
    """Require permission to create file and directory symlinks."""
    target = tmp_path / "symlink-probe"
    target.mkdir()
    file_target = target / "file"
    file_target.touch()
    file_link = tmp_path / "symlink-file-probe"
    directory_link = tmp_path / "symlink-directory-probe"
    try:
        file_link.symlink_to(file_target)
        directory_link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.EACCES, errno.ENOTSUP) and getattr(exc, "winerror", None) != 1314:
            raise
        pytest.skip(f"filesystem cannot create symlinks: {exc}")
    finally:
        file_link.unlink(missing_ok=True)
        if os.name == "nt" and directory_link.is_symlink():  # pragma: no cover - Windows directory links
            directory_link.rmdir()
        else:
            directory_link.unlink(missing_ok=True)
        file_target.unlink()
        target.rmdir()


@pytest.fixture(scope="session")
def parser():
    """Configured Lark parser for SattLine."""
    return create_parser()


@pytest.fixture(scope="session")
def transformer():
    """SLTransformer instance."""
    return SLTransformer()
