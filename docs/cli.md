# `sattline` command line

`check`, `parse`, `query`, `project`, `graphics`, `decode`, `diff`, `corpus` and
`version` wrap the library for people and agents that should not have to write
Python glue. The CLI adds no semantics: every command calls a documented library
entry point and prints one shape of finding.

```
sattline <command> [options]
python -m sattline_parser <command> [options]
```

Every command is read-only. There is no `--fix`, no `--write`, no network
access, no prompt and no watch mode: the CLI reports, and the caller decides.

## Finding shape

Every problem — a source that does not parse, a decoder refusal, a validator
diagnostic — is reported the same way.

Text (default):

```
Steps.s:12:4: Consecutive SFC steps without an intervening SEQTRANSITION
    SEQSTEP Second
    ^
```

```
Broken.s:7:21: unexpected end of file; expected ';', '(', 'LOCALVARIABLES' or 'ModuleDef'
    help: the unit ends before a required ';'; the last construct is incomplete
    ENDDEF (*BasePicture*)
                        ^
```

JSON (`--json`: one document, `--jsonl`: one line per finding then a summary):

```json
{"severity": "error", "message": "Consecutive SFC steps without an intervening SEQTRANSITION",
 "rule": "CONSECUTIVE_SEQUENCE_STEPS", "file": "Steps.s",
 "line": 12, "column": 4, "start": 394, "end": 404,
 "hint": null, "source_line": "   SEQSTEP Second"}
```

`message` is a sentence about the source and `hint` is the actionable part.
`rule` is a machine-only identifier for baselines and diffs; it is never printed
as text. Every payload carries `"schema": "sattline.v1.<command>"`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | success, nothing to report |
| `1` | findings (see `--fail-on` per command) |
| `2` | usage or input problem (bad flag, unreadable file, undecodable bytes) |
| `3` | internal error — a bug; rerun with `--debug` for the traceback |

## `sattline check`

Decode, parse and validate one or more sources.

```bash
sattline check SR/*.s                     # gate a directory
sattline check Broken.s --json            # one JSON document
sattline check Steps.s --jsonl            # stream findings
sattline check - --stdin-name Piped.s < M.s   # stdin needs a display name
sattline check A.s B.s --severity error   # only errors
sattline check Steps.s --rule CONSECUTIVE_SEQUENCE_STEPS
sattline check Steps.s --max-findings 5   # print at most 5, exit still reflects all
sattline check Steps.s --fail-on never    # report but never fail
```

`--fail-on error` (default) fails on error findings, `any` also on warnings,
`never` always exits `0`. `--paths absolute` prints absolute source paths.
Today every validator rule is an error; warnings are reported and counted, and
`--fail-on any` is there for rules that will emit them.

**Scope.** Each file is validated as a single unit, exactly like
`parse_and_validate`: types and variables declared in *other* files of a library
are not resolved. A library unit that references its siblings therefore reports
many `UNDEFINED_VARIABLE` / `UNKNOWN_DATATYPE_NAME` findings. Narrow with
`--rule`, `--severity` or `--max-findings`. A `.g`/`.y` graphics companion is
refused with a message rather than reported as broken source.

Cross-unit resolution needs a project tree, which `sattline project` loads.

## `sattline parse`

Show the structure of one unit without validation noise.

```bash
sattline parse M.s                        # summary
sattline parse M.s --json                 # the same summary as JSON
sattline parse M.s --tree --depth 3       # the AST as JSON, bounded
```

Summary fields: `file`, `program`, `name`, `encoding` (`plain`/`coded`) and
`counts` (module types, submodules, local variables, sequences, equations, graph
objects, interact objects). `encoding` is `coded` for both marker-compressed
text and the binary `.x` framing, `plain` otherwise.

`--tree` emits `{"schema": "sattline.v1.parse", "tree": …}` with source spans.
`--depth` bounds the output: a composite that is not expanded becomes a
placeholder (`"<ModuleDef>"`, `"<12 items>"`) instead of vanishing. `--compact`
puts the JSON on one line. `--tree` always emits JSON.

A source that does not parse is reported as a finding and exits `1` — `parse`
never prints a traceback.

## `sattline query`

Answer one structural question about a unit, as rows you can grep or filter.

```bash
sattline query M.s --what symbols             # declarations (default)
sattline query M.s --what references --name EnableFlag
sattline query M.s --what writers             # assignment targets
sattline query M.s --what callers             # function calls
sattline query M.s --what graph-objects
sattline query M.s --what interact-objects
sattline query M.s --what sequences --module StartMaster/Changelog
sattline query M.s --what symbols --limit 10 --jsonl
```

`--what definitions` is an alias for `symbols`. `--name` filters rows
case-insensitively, `--module` filters by module path (`A/B` for a nested
module), and `--limit` stops after *N* rows.

Rows carry `kind`, `name`, `detail`, `module`, `line`, `column`, `start` and
`end`. A row without a position (a variable, an interact object) reports `null`
there: only graph objects, SFC elements, statements and expressions carry spans.

No matching row exits `1`, so `query` composes in shell tests.

## `sattline project`

Load a project tree: programs, their artifacts, and the dependency graph.

```bash
sattline project SR/                         # every source declared in the root
sattline project SR/*/                       # one root per library directory
sattline project SR/ --targets Start,Master  # only these programs
sattline project SR/ --graph                 # edges only
sattline project SR/ --graph --of Master --depth 2
sattline project SR/ --graph --of Nucleus --reverse
sattline project SR/ --cycles                # only dependency cycles
sattline project SR/ --mode official --lenient --json
```

A root is a **library directory**: the loader resolves artifacts directly inside
it (that is what the ordered lookup indexes), so pass each library directory,
not a directory that merely contains libraries. With no `--targets`, every
program declared directly in the roots is loaded. Draft mode (default) reads
`.s` (falling back to `.x`); official mode reads only `.x`/`.y`/`.z`.

Without `--lenient`, an unresolvable or unparseable artifact is one
`PROJECT_LOAD_ERROR` finding and the exit code is `1`. With `--lenient`, the
rest of the tree still loads, but each skipped program is reported as a
`load-skipped` diagnostic (and still exits `1`): a partial load is never silent.

Program rows report `name`, the artifact extensions actually found (`code`,
`graphics`, `deps`), `sidecar`, `dependencies`, `graphics_records` and `source`.
Graph edges use canonical casefolded identities while program rows keep the
declared casing, so `--of`/`--graph` and the JSON payload always agree. A
declared but unloaded dependency keeps its edge and appears as a `load-skipped`
diagnostic.

`--of` walks outwards from one program (its dependencies, or its dependents with
`--reverse`), bounded by `--depth`. `--cycles` prints each dependency cycle once,
as `a -> b -> a`; any cycle also makes the exit code `1`. `--cache-dir DIR` and
`--no-cache` control the parser caches.

## `sattline graphics`

Read a graphics companion (`.g`/`.y`) and, optionally, correlate it with a
source unit.

```bash
sattline graphics M.y                     # records, picture displays and paths
sattline graphics M.y --asset-paths       # only the paths, one per line
sattline graphics M.y --json
sattline graphics M.y --correlate --source M.s
```

`--correlate` pairs each `CompositeObject` marker in `--source` with its record
in native declaration order and prints `marker #N at line L -> record #R`.

Problem records are reported as findings (`GRAPHICS_RECORD`,
`GRAPHICS_CORRELATION`) and exit `1`. A file that is not a companion, or a
source that does not parse, is refused or reported as one finding.

## `sattline decode`

Turn a compact/coded source into plain text.

```bash
sattline decode M.x                       # plain text on stdout
sattline decode M.x --report              # sizes only, as JSON
sattline decode M.x --json                # the text inside a JSON document
```

`--report` and `--json` are mutually exclusive. An undecodable source is a usage
error (`2`).

## `sattline diff`

Compare two versions of a unit: findings added/removed, and structural counts
that moved.

```bash
sattline diff Old.s New.s
sattline diff Old.s New.s --json
```

Findings are matched by `(rule, message)`, so a moved finding is not a
difference, but a new one is. Any difference exits `1`; identical inputs print
`no differences` and exit `0`.

## `sattline corpus`

Batch triage over a source tree.

```bash
sattline corpus SR/                       # per-file counts, then the histogram
sattline corpus SR/ --summary             # histogram only
sattline corpus SR/ --jobs 8 --json       # parallel, one document
sattline corpus SR/ --fail-on any
```

Every `.s`/`.x` file under the root is parsed and validated as a unit. The
histogram counts findings by rule. Unreadable files are reported as
`READ_ERROR` rather than aborting the run.

`--fail-on error` (default) fails on files with errors, `any` also on warnings,
`never` always exits `0`.

## `sattline version`

```bash
sattline version
sattline version --json
```

The JSON form carries the tool version, the available commands and the schema id
each command emits (`sattline.v1.check`, `sattline.v1.parse`,
`sattline.v1.query`, `sattline.v1.project`, `sattline.v1.graphics`,
`sattline.v1.decode`, `sattline.v1.diff`, `sattline.v1.corpus`,
`sattline.v1.version`), so a client can pin against a contract.

## Source flavors

Every command that reads a source file reads it exactly like
`parse_source_file`, so the three on-disk flavors the workstation writes all
work:

- **plain** Windows-1252 text;
- **marker-compressed** text (a `C` in the syntax-version line, `#xx` codes):
  decoded before parsing, with spans and locations mapped back to the original
  text;
- **byte-coded** `.x` streams (the binary `\x80 3.1` framing): decoded before
  parsing; positions then refer to the decoded text, which is what the editor
  shows.

Undefined Windows-1252 bytes (`0x81 0x8D 0x8F 0x90 0x9D`) are refused outside
comments and tolerated inside `(* … *)`, exactly as the editor accepts them. A
file that cannot be read or decoded is a usage error (`2`), never a crash.
Stdin accepts the same three flavors.

## Shared options

`--json` / `--jsonl` (mutually exclusive) · `--stdin-name PATH` (display name for
`-`) · `--paths given|absolute` · `--debug` (tracebacks for internal errors).

Tracebacks are never printed unless `--debug` is given; parse failures are
findings, not crashes.
