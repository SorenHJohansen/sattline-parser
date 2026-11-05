"""Guards for the grammar vocabulary in ``grammar/constants.py``."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from sattline_parser.grammar import constants
from sattline_parser.grammar.resolved import resolved_grammar

_CONSTANTS_PATH = Path(__file__).resolve().parents[2] / "src" / "sattline_parser" / "grammar" / "constants.py"
_REPO_ROOT = _CONSTANTS_PATH.parents[3]
_LARK_PATH = _REPO_ROOT / "src" / "sattline_parser" / "grammar" / "sattline.lark"
_PYTHON_ROOTS = ("src", "tests", "scripts", "benchmarks")
_CONSTANT_RECEIVERS = frozenset({"const", "constants", "parser_const", "parser_constants"})


def _constant_source() -> str:
    return _CONSTANTS_PATH.read_text(encoding="utf-8")


def _constant_names(source: str) -> list[str]:
    return re.findall(r"^([A-Z][A-Z0-9_]*)\s*(?::\s*Final)?\s*=", source, re.MULTILINE)


def _used_constant_names(source: str) -> set[str]:
    """Names used by the grammar template, another constant, or Python code."""
    used = set(re.findall(r"\{\s*([A-Z][A-Z0-9_]*)\s*\}", _LARK_PATH.read_text(encoding="utf-8")))

    for name in _constant_names(source):
        if len(re.findall(rf"\b{name}\b", source)) > 1:
            used.add(name)

    for root in _PYTHON_ROOTS:
        for path in (_REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" in path.parts or path.resolve() == _CONSTANTS_PATH:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and "constants" in node.module:
                    used.update(alias.name for alias in node.names)
                elif (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in _CONSTANT_RECEIVERS
                ):
                    used.add(node.attr)

    return used


def test_all_contains_every_public_constant_and_no_imported_names() -> None:
    declared = sorted(name for name in vars(constants) if name.isupper() and not name.startswith("_"))

    assert constants.__all__ == declared
    assert "Final" not in constants.__all__


def test_every_constant_is_final() -> None:
    tree = ast.parse(_constant_source())
    bare = [
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id.isupper()
    ]
    assert bare == []

    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id.isupper():
            assert ast.unparse(node.annotation) == "Final", node.target.id


def test_literal_constant_values_are_unique() -> None:
    seen: dict[object, str] = {}
    duplicates: list[tuple[str, str, object]] = []
    for node in ast.parse(_constant_source()).body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            targets = node.targets
            value = node.value
        if value is None or len(targets) != 1:
            continue
        target = targets[0]
        if not isinstance(target, ast.Name) or not target.id.isupper():
            continue
        try:
            literal = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError):
            continue
        if literal in seen:
            duplicates.append((target.id, seen[literal], literal))
        else:
            seen[literal] = target.id

    assert duplicates == []


def test_no_orphan_constant_is_declared() -> None:
    source = _constant_source()
    used = _used_constant_names(source)
    orphans = [name for name in _constant_names(source) if name not in used]

    assert orphans == []


def test_grammar_resolves_without_a_placeholder() -> None:
    text = resolved_grammar()

    assert "{GRAMMAR_" not in text
    assert "STATE_SUFFIX" in text
