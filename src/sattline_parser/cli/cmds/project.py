"""``sattline project`` — what a tree contains and how it depends."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from sattline_parser.project import (
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    LoadValidation,
    ProjectLoadError,
    SattLineProgram,
    SattLineProject,
    code_ext_candidates,
)
from sattline_parser.project._cycles import dependency_cycles

from .._errors import CliError
from .._exit import ExitCode
from .._findings import PROJECT_LOAD_RULE, Finding
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_fail_on, add_output_flags, emit_findings, fails_on, positive_int

__all__ = ["register", "run"]

Edge = dict[str, str]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "project", help="load a project tree: programs, artifacts, dependencies"
    )
    parser.add_argument("root", metavar="ROOT", nargs="+", help="project root(s)")
    add_output_flags(parser)
    parser.add_argument(
        "--mode",
        choices=("draft", "official"),
        default="draft",
        help="which artifacts to resolve (default: draft)",
    )
    parser.add_argument(
        "--targets",
        metavar="A,B",
        help="only load these program names (default: every source under the roots)",
    )
    parser.add_argument("--cache-dir", metavar="DIR", help="parser cache directory")
    parser.add_argument("--no-cache", action="store_true", help="bypass the parser caches")
    parser.add_argument("--lenient", action="store_true", help="continue past unreadable artifacts")
    parser.add_argument(
        "--validate",
        choices=("invoked", "full", "none"),
        default="invoked",
        help=(
            "what to validate: the selected programs plus the module types they invoke "
            "(default), every loaded program, or nothing"
        ),
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="alias for --validate none",
    )
    add_fail_on(parser)
    parser.add_argument("--graph", action="store_true", help="only print the dependency edges")
    parser.add_argument("--of", metavar="NAME", help="restrict the graph to this program")
    parser.add_argument("--reverse", action="store_true", help="follow dependents instead of dependencies")
    parser.add_argument("--depth", type=positive_int, metavar="N", help="limit the graph traversal depth")
    parser.add_argument("--cycles", action="store_true", help="only print dependency cycles")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    try:
        project = _load(args)
    except CliError:
        raise
    except ProjectLoadError as exc:
        # A tree that cannot be loaded is a finding about the tree. Anything
        # else is a bug in this tool and must reach main()'s internal-error path.
        finding = Finding(severity="error", message=f"cannot load project: {exc}", rule=PROJECT_LOAD_RULE)
        emit_findings([finding], args=args, schema="project", extra={"programs": []})
        return int(ExitCode.FINDINGS)
    programs = project.programs()
    graph = project.graph()
    load_diagnostics = project.diagnostics()
    validation_rows = _validation_rows(programs)
    cycles = _cycles(graph.edges)
    edges = _edges(project, args)
    if args.cycles:
        _emit_cycles(cycles, args=args)
    elif args.graph:
        _emit_graph(edges, cycles, args=args)
    else:
        _emit_programs(programs, edges, load_diagnostics, validation_rows, cycles, args=args)
    failing = bool(cycles) or any(
        diagnostic.kind in {LoadDiagnosticKind.DEPENDENCY_CYCLE, LoadDiagnosticKind.LOAD_SKIPPED}
        for diagnostic in load_diagnostics
    )
    if _validation_fails(validation_rows, args.fail_on):
        failing = True
    return int(ExitCode.FINDINGS if failing else ExitCode.OK)


def _validation_rows(programs: Mapping[str, SattLineProgram]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for program in programs.values():
        for diagnostic in program.diagnostics:
            span = diagnostic.span
            rows.append(
                {
                    "program": program.name,
                    "code": diagnostic.code.value,
                    "severity": diagnostic.severity.value,
                    "message": diagnostic.message,
                    "line": None if span is None else span.line,
                    "column": None if span is None else span.column,
                    "tentative": diagnostic.tentative,
                }
            )
    return rows


def _validation_fails(rows: Sequence[Mapping[str, object]], fail_on: str) -> bool:
    return fails_on(
        sum(1 for row in rows if row["severity"] == "error"),
        sum(1 for row in rows if row["severity"] == "warning"),
        fail_on,
    )


def _load(args: argparse.Namespace) -> SattLineProject:
    roots = [Path(root) for root in args.root]
    for root in roots:
        if not root.exists():
            raise CliError(f"cannot read {root}: no such file or directory")
        if not root.is_dir():
            raise CliError(f"cannot read {root}: not a directory")
    mode = LoadMode(args.mode)
    targets = (
        tuple(part.strip() for part in args.targets.split(",") if part.strip())
        if args.targets
        else _discover_targets(roots, mode=mode)
    )
    if not targets:
        roots_text = " ".join(str(root) for root in roots)
        raise CliError(f"no source files directly under {roots_text}; pass each library directory as a root")
    return SattLineProject.load(
        roots,
        mode=mode,
        targets=targets,
        strict=not args.lenient,
        cache_dir=None if args.no_cache else (Path(args.cache_dir) if args.cache_dir else None),
        validate=LoadValidation.NONE if args.no_validate else LoadValidation(args.validate),
    )


def _discover_targets(roots: Sequence[Path], *, mode: LoadMode) -> tuple[str, ...]:
    """Every program name declared *in* the roots, in extension precedence.

    A root is a library directory: the loader indexes the artifacts directly
    inside it, so discovery looks at the same level rather than walking nested
    directories it could never resolve.
    """
    extensions = {extension.lower() for extension in code_ext_candidates(mode)}
    names: set[str] = set()
    for root in roots:
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in extensions:
                names.add(path.stem)
    return tuple(sorted(names))


def _edges(project: SattLineProject, args: argparse.Namespace) -> list[Edge]:
    """Every dependency edge, or the tree traversed from ``--of``.

    Edges use the graph's canonical (casefolded) identities throughout, so
    ``--of``, ``--graph`` and the JSON payload always agree.
    """
    edges: list[Edge] = [{"from": dependent, "to": dependency} for dependent, dependency in project.graph().edges]
    if args.of is None:
        return edges
    return _tree(edges, args.of.casefold(), reverse=args.reverse, depth=args.depth)


def _tree(edges: Sequence[Edge], start: str, *, reverse: bool, depth: int | None) -> list[Edge]:
    """The edges walked outwards from ``start`` (dependencies, or dependents)."""
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        source, target = (edge["to"], edge["from"]) if reverse else (edge["from"], edge["to"])
        adjacency.setdefault(source, []).append(target)
    limit = depth if depth is not None else len(edges) + 1
    visited = {start}
    frontier = [start]
    walked: list[Edge] = []
    for _step in range(limit):
        following: list[str] = []
        for name in frontier:
            for neighbour in adjacency.get(name, ()):
                walked.append({"from": neighbour, "to": name} if reverse else {"from": name, "to": neighbour})
                if neighbour not in visited:
                    visited.add(neighbour)
                    following.append(neighbour)
        if not following:
            break
        frontier = following
    return walked


def _cycles(edges: Sequence[tuple[str, str]]) -> list[list[str]]:
    """Elementary dependency cycles as ordered open paths, each reported once."""
    return [list(cycle[:-1]) for cycle in dependency_cycles(edges)]


def _program_row(program: SattLineProgram) -> dict[str, object]:
    return {
        "name": program.name,
        "code": program.format.code_ext,
        "graphics": program.format.graphics_ext,
        "deps": program.format.deps_ext,
        "sidecar": program.sidecar.value,
        "dependencies": list(program.dependencies),
        "source": str(program.source_path) if program.source_path is not None else None,
        "library": program.library,
        "resolved_base": str(program.resolved_base) if program.resolved_base is not None else None,
    }


def _diagnostic_row(diagnostic: LoadDiagnostic) -> dict[str, object]:
    return {
        "kind": diagnostic.kind.value,
        "program": diagnostic.program,
        "detail": diagnostic.detail,
        "path": str(diagnostic.path) if diagnostic.path is not None else None,
    }


def _emit_programs(
    programs: Mapping[str, SattLineProgram],
    edges: Sequence[Edge],
    diagnostics: Sequence[LoadDiagnostic],
    validation: Sequence[Mapping[str, object]],
    cycles: Sequence[list[str]],
    *,
    args: argparse.Namespace,
) -> None:
    rows = [_program_row(program) for program in programs.values()]
    diagnostics_rows = [_diagnostic_row(diagnostic) for diagnostic in diagnostics]
    if args.json or args.jsonl:
        payload = {
            "schema": f"{SCHEMA_PREFIX}.project",
            "mode": args.mode,
            "programs": rows,
            "edges": list(edges),
            "cycles": list(cycles),
            "diagnostics": diagnostics_rows,
            "validation": list(validation),
        }
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    print(f"programs: {len(rows)}")
    for program in programs.values():
        dependencies = ", ".join(program.dependencies) if program.dependencies else "-"
        library = program.library or "-"
        print(
            f"  {program.name}  library={library} code={program.format.code_ext or '-'} "
            f"graphics={program.format.graphics_ext or '-'} deps={program.format.deps_ext or '-'} "
            f"sidecar={program.sidecar.value} depends on: {dependencies}"
        )
    print(f"edges: {len(edges)}")
    if cycles:
        print("cycles:")
        for cycle in cycles:
            print(f"  {' -> '.join([*cycle, cycle[0]])}")
    if diagnostics_rows:
        print("diagnostics:")
        for row in diagnostics_rows:
            print(f"  {row['kind']} {row['program']}: {row['detail']}")
    if validation:
        print("validation:")
        for row in validation:
            location = ""
            if row["line"] is not None:
                location = f" {row['line']}:{row['column']}"
            tentative = " (tentative)" if row["tentative"] else ""
            print(f"  {row['code']} {row['program']}{location}{tentative}: {row['message']}")


def _emit_graph(edges: Sequence[Edge], cycles: Sequence[list[str]], *, args: argparse.Namespace) -> None:
    if args.json or args.jsonl:
        payload = {"schema": f"{SCHEMA_PREFIX}.project", "edges": list(edges), "cycles": list(cycles)}
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    for edge in edges:
        print(f"{edge['from']} -> {edge['to']}")


def _emit_cycles(cycles: Sequence[list[str]], *, args: argparse.Namespace) -> None:
    if args.json or args.jsonl:
        payload = {"schema": f"{SCHEMA_PREFIX}.project", "cycles": list(cycles)}
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    for cycle in cycles:
        print(" -> ".join([*cycle, cycle[0]]))
