# Command line

The `sattline` command is a JSON-first wrapper over the library. It never
modifies a source tree and has no `--fix`, no network access and no watch mode,
but `project` caches parsed ASTs under the user's cache directory unless
`--no-cache` is given. Every command maps onto a documented library call, and
the source commands report problems in one finding shape. It is designed for
agents, scripts, and CI, not for interactive editing.

```bash
sattline <command> [options]
sattline --debug <command> [options]
python -m sattline_parser <command> [options]
```

There is no `--fix`, no network access, and no watch mode.

## Dispatch and exit codes

```mermaid
flowchart TB
    A["argv"] --> B["build_parser"]
    B --> C{"parse_args"}
    C -->|usage error| U["print message + try --help<br/>exit 2"]
    C -->|ok| D["args.handler(args)"]
    D --> E{"result"}
    E -->|0| OK["exit 0"]
    E -->|1| F["exit 1 findings"]
    E -->|2| U
    E -->|3| I["exit 3 internal"]
    D -->|CliError| U
    D -->|KeyboardInterrupt| K["print interrupted<br/>exit 130"]
    D -->|BrokenPipeError| P["discard stdout<br/>exit 2"]
    D -->|other exception| X{"--debug?"}
    X -->|yes| T["traceback"]
    X -->|no| O["one-line internal error"]
    T --> I
    O --> I
```

| Exit code | Meaning |
| --- | --- |
| `0` | Clean |
| `1` | Findings (or a diff that changed, or a query with no rows) |
| `2` | Usage, input, or output problem (including a closed stdout) |
| `3` | Internal error (a bug) |
| `130` | Interrupted (Ctrl-C), following the shell convention of 128 + SIGINT |

Agents branch on exit codes, not on prose. A traceback is printed only under
`--debug`. `--debug` is a top-level flag, so it comes before the command:
`sattline --debug check program.s`. After the command name it is an unknown
option and exits `2`.

A consumer that closes the output pipe early, as `sattline check SR/*.s | head`
does, stops the report and exits `2`. No explanation is printed, because the
stream that would carry it is the one that closed, and the process does not fall
through to the interpreter's exit flush, which would otherwise report a second
failure and exit `120`.

## Commands

| Command | Maps to | What it answers |
| --- | --- | --- |
| `check` | `parse_and_validate` | Does this source decode, parse, and validate? |
| `parse` | `parse_source_text` | What is the structure of this unit? |
| `query` | `parse_source_text` + AST walk | One structural question: symbols, references, writers, callers, graph objects, interact objects, sequences |
| `rules` | validation rule registry | Which rules exist, what they mean, and whether they are active? |
| `project` | `SattLineProject.load` | What does this tree contain, and how does it depend? |
| `graphics` | `parse_graphics_text` | What bindings and scan messages does this companion have? |
| `decode` | `preprocess_source` | What is this compact/coded source as plain text? |
| `diff` | `analyse` on two units | Which findings and counts moved? |
| `corpus` | `analyse` over a tree | What is the rule histogram for a whole source tree? |
| `version` | package metadata | What tool and schema versions am I talking to? |

### `check`

```bash
sattline check SR/*.s --jsonl
sattline check program.s --rule CONSECUTIVE_SEQUENCE_STEPS --fail-on error
sattline check - --stdin-name editor-buffer.s
```

Reads each source exactly like `parse_source_file` and reports parse-or-decode
failures and validator diagnostics in one shape.

`--rule` accepts a rule id (`SL-V016`), enum name
(`CONSECUTIVE_SEQUENCE_STEPS`), or one of the two synthetic finding ids this
command emits itself: `PARSE_ERROR` and `DECODE_ERROR`. It is repeatable, so
output can be narrowed to one rule. An unknown rule, an inactive rule, or
another command's synthetic id (such as `READ_ERROR`, which only `corpus`
reports) is a usage error (exit `2`), never a silently empty report. See
[`rules`](#rules) for the registry.

`--json` carries `files`: the display name of every input, in the order read,
rendered by the same `--paths` rule as the `file` field of a finding. Stdin
appears under its `--stdin-name`, so `files` always agrees with the findings.

### `parse`

```bash
sattline parse M.s
sattline parse M.s --tree --depth 3
sattline parse M.s --json
sattline parse M.s --json --compact
```

The default output is a structural summary: program name, encoding, and counts
of module types, submodules, local variables, sequences, equation blocks (the
`equationblocks` key), graph objects, and interact objects. The counts cover the
whole module tree, so a nested submodule's declarations and code blocks are
included, and the summary agrees with a `walk` over the picture. `diff` compares
the same counts. `encoding` names the on-disk flavor and is `plain`,
`compressed` (marker-compressed text), or `coded` (a byte-coded stream). A coded
stream stays `coded` even when its decoded text is still marker-compressed.
`--tree` emits the AST as JSON, bounded by `--depth` (default 5). At the limit a
composite value is replaced by a placeholder such as `<ModuleDef>` or
`<12 items>`, so nothing silently disappears. `--compact` prints JSON on one
line instead of indented.

Every `--json` parse document carries `ok` and `findings`. A successful unit has
`ok: true` and an empty `findings`; a parse failure has `ok: false` and the
parse finding. A summary document also carries the structural `counts`; a
`--tree` document carries `tree` instead.

### `query`

```bash
sattline query M.s --what writers --name Counter
sattline query M.s --what symbols --module StartMaster/Changelog
sattline query M.s --what sequences --json --limit 5
```

`--what` accepts `symbols`, `references`, `writers`, `callers`,
`graph-objects`, `interact-objects`, and `sequences`. `symbols` reports module
types, submodules, module instances, variables, parameters, datatypes, and
record fields. Variable, parameter, datatype, and record-field rows carry the
declaration span in `line`, `column`, `start`, and `end`; a record-field row
uses its datatype name as the `module` value. Filters are case-insensitive:
`--name` matches a row name, `--module` matches a slash-separated module path,
and `--limit N` stops after `N` rows. A query with no rows exits `1`, because
"nothing found" is a finding for a caller that expected a hit.

`--json` emits one document with `file`, `ok`, `counts`, `findings`, and `rows`,
so a success and a parse failure are read the same way. A successful query has
`ok: true`, `counts: {"error": 0}`, and an empty `findings`. `--jsonl` streams
the rows only on success; on a parse failure it streams the finding and then the
summary object, like `parse`.

`references` includes variable uses in header, graphics, interact, and
module-layout annotation tails. A bare bound `InVar_`/`OutVar_` name is reported
with detail `unresolved` because the parser does not evidence how the name
resolves. The row carries the tail's source span. A `LitString` tail is a quoted
symbol, not a variable path, and is not reported. Text-object `VarName`
references and `IntObjPickButton` references are ordinary `VarRef` rows, so
filtering the rows on `VarRef` gives every reference in the unit. These rows are
AST introspection, not a graphics-companion binding, and the validator does not
diagnose them. The `GroupConn=` name is not a variable use and is not listed.

### `rules`

```bash
sattline rules
sattline rules SL-V016
sattline rules CONSECUTIVE_SEQUENCE_STEPS --json
```

Lists every rule with its id, enum name, status, and summary. Retired rules are
hidden from the listing unless `--include-retired` is given; a single lookup by
id or name always finds one. `--json` emits one document and `--jsonl` emits one
object per line followed by a summary. An unknown rule exits `2`.

The status is `active` (the validator emits it), `retired` (the form was proved
to load and the check was withdrawn, or another rule already covers it), or
`unimplemented` (a reserved code with no check). The same registry renders the rule table in
[validation.md](validation.md).

### `project`

```bash
sattline project programs/ libs/ --targets MyProgram --json
sattline project programs/ libs/ --graph
sattline project programs/ libs/ --of MyProgram --reverse --depth 2
sattline project programs/ libs/ --validate full --fail-on error
```

A root is a library directory: the loader indexes artifacts directly inside it.
Roots are searched in the order written, and an earlier root wins. The path
holds one library per name, so a root whose directory name repeats an earlier
root is shadowed entirely and contributes no units or targets. When two roots
with different names hold a unit with the same name, only the earlier body is
loaded. When `--targets` is omitted, every source directly under each effective
root is a target.
A missing or unparseable artifact is a load failure: the command reports
`cannot load project` with the underlying error and exits `1`, whatever
`--fail-on` says. When the failure is a body that does not parse, the finding
keeps the parser's sentence, `line`, `column`, and `hint` from the cause, so the
report points at the source rather than only naming the artifact. A recursive
`.l`/`.z` dependency
(`DependencyCycleError`) and a module type that instantiates itself
(`ModuleTypeCycleError`) are load failures too, reported the same way. There is
no partial project: `--fail-on` governs validation findings only.

Each program row reports `distribution` (the resolved companion extension or
`null`), `has_executing_system` (`true`, `false`, or `null` when no companion was
found), and `executing_systems` (one `kind` / `name` / `download` object per
target). A companion that exists but does not parse is a load failure, never an
empty list. See [project.md](project.md#distribution-companion).

| Flag | Meaning |
| --- | --- |
| `--search-path PATH` | Comma-separated roots in lookup order, as an alternative to positional `ROOT...`; backslashes are accepted |
| `--search-path-base DIR` | Resolve relative `--search-path` entries under `DIR` |
| `--mode draft\|official` | Which artifacts to resolve. Default `draft` |
| `--targets A,B` | Only load these program names. Default: every source under the roots |
| `--workers N` | Parse bodies in `N` processes, 1 to 32. Default `min(8, cpu_count)`; `1` parses in this process |
| `--cache-dir DIR` | Parser cache directory |
| `--no-cache` | Bypass the project caches |
| `--validate invoked\|full\|none` | What to validate. Default `invoked` |
| `--fail-on none\|error` | Whether a validation finding fails the run. Default `error` |

The project caches live under `$XDG_CACHE_HOME/sattline-parser/project` (or
`~/.cache/sattline-parser/project`) unless `--cache-dir` names another private
directory; a relative `XDG_CACHE_HOME` is ignored, and an unknown home directory
disables the cache. `--no-cache` makes the load hermetic: the project caches
neither read nor write. The compiled grammar cache under the temporary directory
is independent of this flag. A first load in an empty directory writes the
cache; every later load of an unchanged tree skips parsing. The directory holds
parsed ASTs of the loaded sources, so keep it private. On Windows the cache is
used only when the directory's security descriptor proves that this user owns it
and that no other trustee can write it; otherwise the caches stay disabled, so a
shared `--cache-dir` never serves a planted pickle.

`--cycles` is gone, and the JSON payload no longer carries a `cycles` key: a
recursive dependency chain or a self-instantiating module type is a structural
load error, so the command reports `cannot load project` and exits `1` instead
of listing cycles.

### `graphics`

```bash
sattline graphics drawing.y
sattline graphics drawing.y --json
```

Refuses a `.s`/`.x` source. Conversely, `check`, `parse`, `query`, `decode`, and
`diff` refuse a `.g`/`.y` graphics companion and a `.p`/`.q` distribution
companion, so a companion is never reported as broken source. The refusal uses
the name that identifies the input: the path itself, or `--stdin-name` when the
input is `-`, so `sattline check --stdin-name x.g -` is refused exactly like a
`.g` path, and `sattline graphics --stdin-name x.s -` is refused exactly like a
`.s` path. Stdin requires `--stdin-name`, as for every source command.

A companion larger than the library's 4 MiB limit is refused as an input
problem (exit `2`) from its size, before its bytes are read. Stdin cannot be
stat'ed, so its length is checked after it has been read.

A scan message is a finding, whether its severity is `warning` (an expression the
grammar could not parse) or `error` (a malformed record), so any scan message
exits `1`: the companion was only partly understood. The message is reduced to
one sentence; the expression parser's expected-token dump and token names are
not reproduced, because the finding already carries the file position and the
raw expression.

### `decode`

```bash
sattline decode coded.x
sattline decode coded.x --report
sattline decode coded.x --json
```

Prints the decoded text by default, a JSON report with `--report`, or the text
inside a JSON document with `--json`.

The report carries `file`, `encoding`, `original_length`, and `decoded_length`.
`encoding` is the same three-way value as `parse`: `plain`, `compressed`
(marker-compressed text), or `coded` (a byte-coded stream). A coded stream stays
`coded` even when the text it decodes to is still marker-compressed.

### `diff`

```bash
sattline diff Program.x Program.s
sattline diff Program.x Program.s --json
```

A SattLine program or library is one unit made of four files: the code body,
the dependency sidecar, the graphics companion, and the distribution companion.
`diff` compares the
official `.x` code body of a unit with its draft `.s` code body. In a unit the
two versions are the official `.x` and the draft `.s`, never two `.s` files;
the command itself accepts any two code sources. It compares findings by
`(rule, message)` and compares structural counts. It is a regression aid, not a
semantic diff. Exit `1` when anything changed. When either side does not parse,
`counts.changed` is empty: there is no comparable summary, and the parse failure
is already reported as a finding rather than as every count moving from `null`.

### `corpus`

```bash
sattline corpus tests/fixtures/corpus --summary
sattline corpus src --jobs 8 --json
```

Scans for `.s`/`.x` recursively. `--jobs N` uses a process pool of 1 to 32
workers and produces the same rows in the same order as a serial run. A worker
returns only counts, so no parser, counter, or source text is shared between
jobs. A pool that cannot start, or one whose worker dies, falls back to scanning
in this process with a warning on stderr. The output is a rule histogram plus
the failing files, or a full JSON result unless `--summary` is given.

### `version`

```bash
sattline version
sattline version --json
```

The JSON payload lists every command and its schema id, so a client can verify
compatibility before parsing output.

## Output modes

| Flag | Effect |
| --- | --- |
| (none) | Human-readable text |
| `--json` | One JSON document |
| `--jsonl` | Command-specific stream, described below |
| `--sarif` | A SARIF 2.1.0 log for code scanning (`check`, `project`); exclusive with `--json` and `--jsonl` |

`--json` and `--jsonl` are mutually exclusive. Findings are never printed as a
second document alongside a JSON payload: they ride inside the same object.

Output never fails on a character the stream cannot encode. A source character
that is outside the stream's encoding (the library maps an undefined
Windows-1252 byte inside a comment to U+FFFD) is escaped with a backslash, so a
cp1252 terminal still prints the report and a JSON escape parses back to the
same character.

`--jsonl` does not mean the same thing in every command, because a command that
reports one unit has nothing to stream:

| Command | `--jsonl` output |
| --- | --- |
| `check` | One finding object per line, then a summary object |
| `rules` | One rule object per line, then a summary object |
| `query` | One row object per line on success; the finding then a summary object on failure |
| `parse` | One compact summary document on success; the finding then a summary object on failure |
| `project` | One compact document |
| `graphics` | One compact document |
| `diff` | One compact document |
| `corpus` | One compact document |
| `decode` | Not accepted; use `--report` or `--json` |
| `version` | Not accepted; use `--json` |

The finding-reporting commands stream the same shape on failure: one finding
object per line, then one summary object with `summary: true`.

## The finding shape

`check`, `parse`, `query`, and `graphics` report a problem as one `Finding`:

```json
{
  "severity": "error",
  "message": "Reference to undefined variable 'Counter'",
  "rule": "UNDEFINED_VARIABLE",
  "file": "program.s",
  "line": 12,
  "column": 20,
  "start": 345,
  "end": 354,
  "hint": null,
  "source_line": "   Total = Counter + 1;"
}
```

| Field | Meaning |
| --- | --- |
| `severity` | `error` for parse, decode, project-load, and validation findings; `warning` for graphics scan messages |
| `message` | A sentence about the source |
| `rule` | Machine-only id: `PARSE_ERROR`, `DECODE_ERROR`, `PROJECT_LOAD_ERROR`, `PROJECT_QUERY_ERROR`, `GRAPHICS_SCAN`, a `DiagnosticCode` enum name such as `UNDEFINED_VARIABLE` (`SL-V019` is its id), or a corpus read error |
| `file` | Display path |
| `line`, `column` | One-based location in the original source, or `null` when the failure has no position, as with a decode error |
| `start`, `end` | Zero-based character range in the original source, or `null` when no range is known, as with a parse error or a decode error |
| `hint` | Actionable sentence, when one is known |
| `source_line` | The original source line at `line`, or `null` |

A rule id is never printed as prose. It exists for baselines, filters, and
diffs.

The document-level `ok` field is present in every `check`, `parse`, and `query`
JSON document, and is `true` only when the document carries no finding of any
severity. A `graphics` warning therefore makes `ok` `false` and the exit
code `1`, exactly like an error.

`sattline project --json` does not use `Finding`. Its payload carries:

| Key | Shape |
| --- | --- |
| `programs` | One row per loaded artifact: `name`, `code`, `graphics`, `deps`, `distribution`, `sidecar`, `dependencies`, `source`, `library`, `resolved_base`, `has_executing_system`, `executing_systems` |
| `edges` | `{"from": dependent, "to": dependency}` over casefolded names |
| `diagnostics` | One row per non-fatal load condition: `kind` (`sidecar-missing`, `sidecar-elsewhere`, `sidecar-empty`, `sidecar-family-mismatch`, or `folded-name-collision`), `program`, `detail`, `path` |
| `validation` | One row per diagnostic: `program`, `code` (`SL-V###`), `message`, `line`, `column` |
| `findings` | Present only when the tree could not be loaded at all: one `Finding` with rule `PROJECT_LOAD_ERROR`, or when `--of` names a program outside the graph: one `Finding` with rule `PROJECT_QUERY_ERROR` |

`--graph` emits `edges` and `validation` and prints the validation rows in text
mode, so a finding still visible in the normal report is never hidden by the
graph projection.

A validation row has no `severity`, because every row it carries is an error.
`line` and `column` are `null` when the diagnostic has no span.

`sattline diff` reports `FindingDelta` rows instead: `rule`, `message`, and
`count`, split into `findings.added` and `findings.removed`, plus
`counts.changed`.

## SARIF output

`sattline check --sarif` and `sattline project --sarif` emit a SARIF 2.1.0 log
for a code-scanning service. The mapping is fixed:

| SARIF field | Source |
| --- | --- |
| `runs[0].tool.driver.name` | `sattline` |
| `runs[0].tool.driver.version` | the package version |
| `runs[0].tool.driver.rules[]` | one descriptor per rule that appears, sorted by id |
| `results[].ruleId` | the `SL-V###` id for a validation finding, or the synthetic finding id |
| `results[].level` | the finding severity, `error` or `warning` |
| `results[].message` | the finding message, with `hint` folded into a `markdown` variant when present |
| `results[].locations[]` | the finding file as a repository-relative, percent-encoded artifact URI when its resolved path is under the working directory, otherwise an absolute file URI; `startLine` and `startColumn` when known |

A result without a location still appears, so a project-load failure is not
dropped. `--sarif` is exclusive with `--json` and `--jsonl`, and on `project` it
also refuses `--of` and `--graph`: asking for two output shapes, or for a
SARIF document of one graph slice, is a usage error. `--max-findings` does not
apply to it, and the exit code is the same as for text output.

## Shared flags

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--debug` | top level | Print loader progress, the parser failure log, and a traceback for internal errors. It comes before the command |
| `--stdin-name PATH` | source commands | Required when reading `-`, so findings are attributable; a companion suffix here is refused like a companion path |
| `--paths given\|absolute` | source commands | How to render paths, in findings and in the document-level `file` key. Default `given` |
| `--rule RULE` | `check` | Filter by rule id or enum name, repeatable; only this command's own synthetic ids (`PARSE_ERROR`, `DECODE_ERROR`) are accepted |
| `--max-findings N` | `check` | Limit printed findings; `0` prints none, a negative value is a usage error, the exit code still reflects all of them, and the withheld count is noted once on stderr |
| `--limit N` | `query` | Stop after `N` rows |
| `--fail-on none\|error` | `check`, `project`, `corpus` | Which findings make the exit code `1` |
| `--compact` | `parse` | Emit JSON on one line |
| `--sarif` | `check`, `project` | Emit a SARIF 2.1.0 log instead of text or JSON |
| `--depth N` | `parse --tree`, `project --of` | Bound output or traversal |

"Source commands" means `check`, `parse`, `query`, `graphics`, `decode`, and
`diff`: the commands that read a source unit or a companion through the same
input layer.

## JSON schemas

Every payload is tagged with `sattline.v1.<command>`:

| Command | Schema |
| --- | --- |
| `check` | `sattline.v1.check` |
| `parse` | `sattline.v1.parse` |
| `query` | `sattline.v1.query` |
| `project` | `sattline.v1.project` |
| `graphics` | `sattline.v1.graphics` |
| `decode` | `sattline.v1.decode` |
| `diff` | `sattline.v1.diff` |
| `corpus` | `sattline.v1.corpus` |
| `rules` | `sattline.v1.rules` |
| `version` | `sattline.v1.version` |

`sattline version --json` is the authoritative list. A schema change is a
public change and must be called out in the changelog.

## Input handling

`read_source` mirrors `parse_source_file`:

- a file is read as bytes, decoded as cp1252, and coded streams are decoded
  first;
- stdin is read as bytes and requires `--stdin-name`;
- a decode failure becomes `CliError` and exit `2`;
- marker-compressed text is left as written so provenance stays anchored to the
  original source;
- `--paths absolute` resolves the display path, in findings and in the
  document-level `file` key.

## Tests that pin the CLI

| Test | What it protects |
| --- | --- |
| `tests/cli/test_cli_core.py` | Dispatch, exit codes, shared flags |
| `tests/cli/test_cli_check.py` | Finding shape and filters |
| `tests/cli/test_cli_parse.py` | Summary and tree output |
| `tests/cli/test_cli_query.py` | Query kinds and filters |
| `tests/cli/test_cli_rules.py` | Rule registry listing and lookup |
| `tests/cli/test_cli_project.py` | Project output and graph |
| `tests/cli/test_cli_project_validation.py` | Validation scope output and `--fail-on` |
| `tests/cli/test_cli_graphics.py` | Companion output and refusal |
| `tests/cli/test_cli_decode_diff_corpus.py` | Decode, diff, and corpus |
| `tests/cli/test_cli_coded.py` | Coded input through the CLI |
