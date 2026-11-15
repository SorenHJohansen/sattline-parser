"""``sattline project`` — what a tree contains and how it depends."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from sattline_parser.__version__ import __version__
from sattline_parser.project import (
    DistributionTarget,
    LoadDiagnostic,
    LoadMode,
    LoadValidation,
    ProjectLoadError,
    SattLineProgram,
    SattLineProject,
    code_ext_candidates,
    parse_search_path,
)

from .._errors import CliError
from .._exit import ExitCode
from .._findings import PROJECT_LOAD_RULE, PROJECT_QUERY_RULE, Finding
from .._json import SCHEMA_PREFIX, dumps
from ._common import (
    add_fail_on,
    add_output_flags,
    add_sarif_flag,
    bounded_positive_int,
    emit_findings,
    emit_sarif,
    fails_on,
    positive_int,
    require_plain_output,
)

__all__ = ["register", "run"]

Edge = dict[str, str]

#: Upper bound on the default worker count: past a handful of processes the
#: load is bounded by memory and IPC rather than by cores.
_MAX_DEFAULT_WORKERS = 8

#: Upper bound a caller may request explicitly. Past this the load is bounded
#: by memory and IPC, and an unbounded request can exhaust the machine.
_MAX_WORKERS = 32


def _default_cache_dir() -> Path | None:
    """Where a load caches its per-file ASTs when ``--cache-dir`` is not given.

    The cache is private to one user and is validated against the source before
    it is trusted, so a default location is what makes a repeated load skip
    parsing instead of re-reading the tree. ``None`` means the cache is off: no
    home directory is known, or ``XDG_CACHE_HOME`` is relative and would put the
    cache inside whatever tree the command happens to run in.
    """
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        candidate = Path(base)
        return candidate / "sattline-parser" / "project" if candidate.is_absolute() else None
    try:
        return Path.home() / ".cache" / "sattline-parser" / "project"
    except RuntimeError:
        # No home directory can be determined (an unusual service context), so
        # run uncached instead of failing the command.
        return None


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "project", help="load a project tree: programs, artifacts, dependencies"
    )
    parser.add_argument(
        "root",
        metavar="ROOT",
        nargs="*",
        help="project root(s), in lookup order; earlier roots win",
    )
    add_output_flags(parser)
    add_sarif_flag(parser)
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
    parser.add_argument(
        "--search-path",
        metavar="PATH",
        help=(
            "comma-separated roots, in lookup order (earlier wins); accepts backslashes, "
            "an alternative to the positional roots"
        ),
    )
    parser.add_argument(
        "--search-path-base",
        metavar="DIR",
        help="resolve relative --search-path entries under DIR",
    )
    parser.add_argument(
        "--cache-dir",
        metavar="DIR",
        help="parser cache directory (default: $XDG_CACHE_HOME/sattline-parser/project)",
    )
    parser.add_argument("--no-cache", action="store_true", help="bypass the parser caches")
    parser.add_argument(
        "--workers",
        type=bounded_positive_int(_MAX_WORKERS),
        metavar="N",
        default=_default_workers(),
        help=(
            "parse program bodies in N processes (default: %(default)s, at most "
            f"{_MAX_WORKERS}; 1 parses in this process)"
        ),
    )
    parser.add_argument(
        "--validate",
        choices=("invoked", "full", "none"),
        default="invoked",
        help=(
            "what to validate: the selected programs plus the module types they invoke "
            "(default), every loaded program, or nothing"
        ),
    )
    add_fail_on(parser)
    parser.add_argument("--graph", action="store_true", help="print the dependency edges and validation rows")
    parser.add_argument("--of", metavar="NAME", help="restrict the graph to this program")
    parser.add_argument("--reverse", action="store_true", help="follow dependents instead of dependencies")
    parser.add_argument("--depth", type=positive_int, metavar="N", help="limit the graph traversal depth")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    require_plain_output(args)
    if args.sarif and (args.of is not None or args.graph):
        raise CliError("--sarif cannot be combined with --of or --graph")
    try:
        project = _load(args)
    except CliError:
        raise
    except ProjectLoadError as exc:
        # A tree that cannot be loaded is a finding about the tree. Anything
        # else is a bug in this tool and must reach main()'s internal-error path.
        finding = Finding(severity="error", message=f"cannot load project: {exc}", rule=PROJECT_LOAD_RULE)
        _report_findings(
            [finding],
            args=args,
            extra={"programs": [], "edges": [], "diagnostics": [], "validation": []},
        )
        return int(ExitCode.FINDINGS)
    programs = project.programs()
    load_diagnostics = project.diagnostics()
    validation_rows = _validation_rows(programs)
    if args.of is not None and args.of.casefold() not in {name.casefold() for name in programs}:
        finding = Finding(
            severity="error",
            message=f"program {args.of!r} is not in the loaded graph",
            rule=PROJECT_QUERY_RULE,
        )
        _report_findings(
            [finding],
            args=args,
            extra={"programs": [], "edges": [], "diagnostics": [], "validation": []},
        )
        return int(ExitCode.FINDINGS)
    edges = _edges(project, args)
    if args.sarif:
        emit_sarif(_sarif_findings(programs), version=__version__)
    elif args.graph:
        _emit_graph(edges, validation_rows, args=args)
    else:
        _emit_programs(programs, edges, load_diagnostics, validation_rows, args=args)
    failing = _validation_fails(validation_rows, args.fail_on)
    return int(ExitCode.FINDINGS if failing else ExitCode.OK)


def _report_findings(findings: Sequence[Finding], *, args: argparse.Namespace, extra: Mapping[str, object]) -> None:
    """Emit one-off findings as SARIF, JSON, JSON lines, or text."""
    if args.sarif:
        emit_sarif(findings, version=__version__)
        return
    emit_findings(findings, args=args, schema="project", extra=extra)


def _sarif_findings(programs: Mapping[str, SattLineProgram]) -> list[Finding]:
    """Validation findings for a SARIF log, with each program's source path.

    The JSON rows carry the program name rather than the path, because a graph
    view is about units. SARIF annotates files, so the source path is the
    location here.
    """
    findings: list[Finding] = []
    for program in programs.values():
        location = str(program.source_path) if program.source_path is not None else None
        for diagnostic in program.diagnostics:
            span = diagnostic.span
            findings.append(
                Finding(
                    severity="error",
                    message=diagnostic.message,
                    rule=diagnostic.code.value,
                    file=location,
                    line=None if span is None else span.line,
                    column=None if span is None else span.column,
                )
            )
    return findings


def _validation_rows(programs: Mapping[str, SattLineProgram]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for program in programs.values():
        for diagnostic in program.diagnostics:
            span = diagnostic.span
            rows.append(
                {
                    "program": program.name,
                    "code": diagnostic.code.value,
                    "message": diagnostic.message,
                    "line": None if span is None else span.line,
                    "column": None if span is None else span.column,
                }
            )
    return rows


def _validation_fails(rows: Sequence[Mapping[str, object]], fail_on: str) -> bool:
    return fails_on(len(rows), fail_on)


def _debug_sink(message: str) -> None:
    """Where ``--debug`` sends the loader's progress and the parser's failures."""
    print(f"debug: {message}", file=sys.stderr)


def _roots(args: argparse.Namespace) -> list[Path]:
    """The lookup roots, from the positional form or the path-list notation."""
    if args.search_path and args.root:
        raise CliError("use either ROOT... or --search-path, not both")
    if args.search_path_base and not args.search_path:
        raise CliError("--search-path-base requires --search-path")
    if args.search_path:
        base = Path(args.search_path_base) if args.search_path_base else None
        try:
            return list(parse_search_path(args.search_path, base=base))
        except ValueError as exc:
            raise CliError(str(exc)) from exc
    if not args.root:
        raise CliError("expected at least one root, or --search-path")
    return [Path(root) for root in args.root]


def _load(args: argparse.Namespace) -> SattLineProject:
    roots = _roots(args)
    for root in roots:
        try:
            present = root.exists()
            is_dir = root.is_dir()
        except OSError as exc:
            raise CliError(f"cannot read {root}: {exc.strerror or exc}") from exc
        if not present:
            raise CliError(f"cannot read {root}: no such file or directory")
        if not is_dir:
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
        debug=_debug_sink if args.debug else None,
        cache_dir=_cache_dir(args),
        validate=LoadValidation(args.validate),
        workers=args.workers,
    )


def _cache_dir(args: argparse.Namespace) -> Path | None:
    """The cache directory for this load, or ``None`` when caching is off."""
    if args.no_cache:
        return None
    if args.cache_dir:
        return Path(args.cache_dir)
    return _default_cache_dir()


def _default_workers() -> int:
    """How many parse processes a load uses when ``--workers`` is not given.

    A project load is parsing: 99% of the time is spent decoding and parsing
    bodies, which is CPU-bound and independent per file. The cap keeps a very
    wide machine from paying more in memory than the wall clock it wins.
    """
    return max(1, min(_MAX_DEFAULT_WORKERS, os.cpu_count() or 1))


def _discover_targets(roots: Sequence[Path], *, mode: LoadMode) -> tuple[str, ...]:
    """Every program name declared *in* the roots, in extension precedence.

    A root is a library directory: the loader indexes the artifacts directly
    inside it, so discovery looks at the same level rather than walking nested
    directories it could never resolve.
    """
    extensions = {extension.lower() for extension in code_ext_candidates(mode)}
    names: set[str] = set()
    for root in roots:
        names.update(path.stem for path in _root_entries(root) if path.is_file() and path.suffix.lower() in extensions)
    return tuple(sorted(names))


def _root_entries(root: Path) -> list[Path]:
    """The direct entries of one root, reported as a bad input rather than a crash."""
    try:
        return list(root.iterdir())
    except OSError as exc:
        raise CliError(f"cannot read {root}: {exc.strerror or exc}") from exc


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


def _program_row(program: SattLineProgram) -> dict[str, object]:
    return {
        "name": program.name,
        "code": program.format.code_ext,
        "graphics": program.format.graphics_ext,
        "deps": program.format.deps_ext,
        "distribution": program.format.distribution_ext,
        "sidecar": program.sidecar.value,
        "dependencies": list(program.dependencies),
        "source": str(program.source_path) if program.source_path is not None else None,
        "library": program.library,
        "resolved_base": str(program.resolved_base) if program.resolved_base is not None else None,
        "has_executing_system": program.has_executing_system,
        "executing_systems": [_executing_system_row(target) for target in _executing_targets(program)],
    }


def _executing_targets(program: SattLineProgram) -> Sequence[DistributionTarget]:
    if program.distribution is None:
        return ()
    return program.distribution.executing_systems


def _executing_system_row(target: DistributionTarget) -> dict[str, object]:
    return {
        "kind": target.kind,
        "name": target.name,
        "download": target.download,
    }


def _executing_summary(program: SattLineProgram) -> str:
    """A short text form of the executing-system answer: yes, no, or unknown."""
    answer = program.has_executing_system
    if answer is None:
        return "-"
    if not answer:
        return "no"
    return "yes (" + ", ".join(target.name for target in _executing_targets(program)) + ")"


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
            "diagnostics": diagnostics_rows,
            "validation": list(validation),
        }
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    print(f"programs: {len(rows)}")
    for program in programs.values():
        dependencies = ", ".join(program.dependencies) if program.dependencies else "-"
        library = program.library or "-"
        executing = _executing_summary(program)
        print(
            f"  {program.name}  library={library} code={program.format.code_ext or '-'} "
            f"graphics={program.format.graphics_ext or '-'} deps={program.format.deps_ext or '-'} "
            f"distribution={program.format.distribution_ext or '-'} exec={executing} "
            f"sidecar={program.sidecar.value} depends on: {dependencies}"
        )
    print(f"edges: {len(edges)}")
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
            print(f"  {row['code']} {row['program']}{location}: {row['message']}")


def _emit_graph(
    edges: Sequence[Edge],
    validation: Sequence[Mapping[str, object]],
    *,
    args: argparse.Namespace,
) -> None:
    if args.json or args.jsonl:
        payload = {
            "schema": f"{SCHEMA_PREFIX}.project",
            "edges": list(edges),
            "validation": list(validation),
        }
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    for edge in edges:
        print(f"{edge['from']} -> {edge['to']}")
    if validation:
        print("validation:")
        for row in validation:
            location = ""
            if row["line"] is not None:
                location = f" {row['line']}:{row['column']}"
            print(f"  {row['code']} {row['program']}{location}: {row['message']}")
