"""Shared pytest fixtures and test utilities."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sattline_parser.api import create_sl_parser
from sattline_parser.transformer.sl_transformer import SLTransformer

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(scope="session")
def parser():
    """Configured Lark parser for SattLine."""
    return create_sl_parser()


@pytest.fixture(scope="session")
def transformer():
    """SLTransformer instance."""
    return SLTransformer()
