"""Boundary test: the model layer must not import Lark."""

from __future__ import annotations

import ast
from pathlib import Path

_MODELS = Path(__file__).resolve().parents[2] / "src" / "sattline_parser" / "models"


def test_models_do_not_import_lark() -> None:
    offenders: list[str] = []
    for path in sorted(_MODELS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            if any(module == "lark" or module.startswith("lark.") for module in modules):
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == []
