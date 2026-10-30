"""``sattline project`` — what a tree contains and how it depends."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from sattline_parser.project import (
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    SattLineProgram,
    SattLineProject,
    code_ext_candidates,
)

from .._errors import CliError
from .._exit import ExitCode
from .._findings import Finding
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_output_flags, emit_findings

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
    parser.add_argument("--graph", action="store_true", help="only print the dependency edges")
    parser.add_argument("--of", metavar="NAME", help="restrict the graph to this program")
    parser.add_argument("--reverse", action="store_true", help="follow dependents instead of dependencies")
    parser.add_argument("--depth", type=_positive_int, metavar="N", help="limit the graph traversal depth")
    parser.add_argument("--cycles", action="store_true", help="only print dependency cycles")
    parser.set_defaults(handler=run)


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def run(args: argparse.Namespace) -> int:
    try:
        project = _load(args)
    except CliError:
        raise
    except Exception as exc:  # noqa: BLE001 - a broken tree is a finding, not a crash
        finding = Finding(severity="error", message=f"cannot load project: {exc}", rule="PROJECT_LOAD_ERROR")
        emit_findings([finding], args=args, schema="project", extra={"programs": []})
        return int(ExitCode.FINDINGS)
    programs = project.programs()
    graph = project.graph()
    load_diagnostics = project.diagnostics()
    cycles = _cycles(graph.edges)
    edges = _edges(project, args)
    if args.cycles:
        _emit_cycles(cycles, args=args)
    elif args.graph:
        _emit_graph(edges, cycles, args=args)
    else:
        _emit_programs(programs, edges, load_diagnostics, cycles, args=args)
    failing = bool(cycles) or any(
        diagnostic.kind in {LoadDiagnosticKind.DEPENDENCY_CYCLE, LoadDiagnosticKind.LOAD_SKIPPED}
        for diagnostic in load_diagnostics
    )
    return int(ExitCode.FINDINGS if failing else ExitCode.OK)


def _load(args: argparse.Namespace) -> SattLineProject:
    roots = [Path(root) for root in args.root]
    for root in roots:
        if not root.exists():
            raise CliError(f"cannot read {root}: no such file or directory")
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


def _strongly_connected_components(adjacency: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """Tarjan's algorithm, iterative so a deep graph cannot exhaust the stack."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0
    nodes = sorted({*adjacency, *(target for targets in adjacency.values() for target in targets)})
    for root in nodes:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, position = work[-1]
            if position == 0:
                index[node] = counter
                low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            targets = adjacency.get(node, ())
            if position < len(targets):
                work[-1] = (node, position + 1)
                neighbour = targets[position]
                if neighbour not in index:
                    work.append((neighbour, 0))
                elif neighbour in on_stack:
                    low[node] = min(low[node], index[neighbour])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
    return components


def _cyclic_components(adjacency: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """The components that hold a cycle, members sorted, in a stable order."""
    cyclic: list[list[str]] = []
    for component in _strongly_connected_components(adjacency):
        if len(component) > 1:
            cyclic.append(sorted(component))
        elif component[0] in adjacency.get(component[0], ()):
            cyclic.append(component)
    return sorted(cyclic)


def _walk_cycles(
    start: str,
    adjacency: Mapping[str, Sequence[str]],
    seen: set[frozenset[str]],
    found: list[list[str]],
) -> None:
    """Enumerate the cycles through ``start``, all of which stay inside its component."""
    trail = [start]
    iterators = [iter(adjacency.get(start, ()))]
    while iterators:
        try:
            neighbour = next(iterators[-1])
        except StopIteration:
            iterators.pop()
            trail.pop()
            continue
        if neighbour in trail:
            cycle = trail[trail.index(neighbour) :]
            key = frozenset(cycle)
            if key not in seen:
                seen.add(key)
                found.append(sorted(cycle))
            continue
        trail.append(neighbour)
        iterators.append(iter(adjacency.get(neighbour, ())))


def _cycles(edges: Sequence[tuple[str, str]]) -> list[list[str]]:
    """Dependency cycles, each reported once with its members sorted.

    Only strongly connected components can contain a cycle, so the search is
    confined to those. An acyclic graph, however many paths it has, costs one
    linear pass instead of one walk per path.
    """
    adjacency: dict[str, list[str]] = {}
    for dependent, dependency in edges:
        adjacency.setdefault(dependent, []).append(dependency)
    found: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    for component in _cyclic_components(adjacency):
        members = set(component)
        local = {node: [target for target in adjacency.get(node, ()) if target in members] for node in component}
        for start in component:
            _walk_cycles(start, local, seen, found)
    return found


def _program_row(program: SattLineProgram) -> dict[str, object]:
    return {
        "name": program.name,
        "code": program.format.code_ext,
        "graphics": program.format.graphics_ext,
        "deps": program.format.deps_ext,
        "sidecar": program.sidecar.value,
        "dependencies": list(program.dependencies),
        "source": str(program.source_path) if program.source_path is not None else None,
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
        }
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    print(f"programs: {len(rows)}")
    for program in programs.values():
        dependencies = ", ".join(program.dependencies) if program.dependencies else "-"
        print(
            f"  {program.name}  code={program.format.code_ext or '-'} graphics={program.format.graphics_ext or '-'} "
            f"deps={program.format.deps_ext or '-'} sidecar={program.sidecar.value} depends on: {dependencies}"
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
