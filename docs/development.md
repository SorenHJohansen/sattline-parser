# Development

## Setup

Requires Python 3.12 or newer.

```bash
git clone https://github.com/SorenHJohansen/sattline-parser.git
cd sattline-parser
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`uv` is the CI standard and the lockfile source:

```bash
uv sync --frozen --all-extras
```

The `fuzz` extra is separate because Atheris is Linux and FreeBSD only:

```bash
pip install -e ".[dev,fuzz]"
```

## Repository map

| Path | Role |
| --- | --- |
| `src/sattline_parser/` | The package |
| `docs/` | This documentation |
| `tests/` | Parser, project, CLI, builtins, packaging suites |
| `scripts/` | Coverage gate, catalogue generator, docs checks, probes, profiling |
| `.github/workflows/` | CI, fuzz, docs, publish |
| `.clusterfuzzlite/` | Continuous fuzzing configuration |
| `.opencode/skills/` | Repo-local skill with map, recipes, and verification ladder |
| `.opencode/commands/` | Repo-local commands: `verify`, `release`, `review` |
| `.opencode/agents/` | Repo-local subagents, including the read-only reviewer |
| `AGENTS.md` | AI control-plane entry point |
| `README.md` | Public entry point |
| `CHANGELOG.md` | Release history, assembled from the fragments |
| `changelog.d/` | One fragment per user-visible change, named `<slug>.<type>.md` |

## Workflow

```mermaid
flowchart LR
    A["start from owning file, symbol, or failing command"] --> B["smallest grounded edit"]
    B --> C["first focused validation<br/>pytest tests/parser or a targeted file"]
    C --> D{"passes?"}
    D -->|no| B
    D -->|yes| E["widen: ruff, pyright, pre-commit"]
    E --> F["full pytest"]
    F --> G["branch coverage script"]
    G --> H["update docs and add a changelog fragment"]
    H --> I["feature branch, pull request"]
```

Rules:

1. Never commit directly to `main`. Work on a feature branch and land through a
   pull request.
2. Never commit, push, tag, merge, open a pull request, or delete a branch
   without explicit permission for that specific action. Propose the command,
   then wait.
3. Start from the owning file. A parser bug belongs in `grammar/`,
   `source_io.py`, or `transformer/`; a rule bug belongs in `validation/`; a
   discovery bug belongs in `project/`.
4. Make the smallest edit that tests the hypothesis, then run the first focused
   check immediately. Widen only after it passes.
5. Prefer a cohesive module that exceeds 500 lines over a mechanical
   `_part1`/`_part2` split. Split when the split is a real responsibility
   boundary.
6. Keep touched Python files Pyright strict-clean.
7. Do not add imports from consumer tooling. This package ships standalone on
   PyPI and must stay self-contained.
8. Back every new rule or data table with something reproducible: a fixture, a
   public manual, or a black-box check. Never add data extracted from
   third-party binaries.

## Writing style

The repository follows the global rules in `AGENTS.md`:

- No dashes used as punctuation. Use a comma, a colon, a full stop,
  parentheses, or a new sentence. Hyphens inside compound words and
  identifiers are normal text and stay.
- Describe behaviour, not origin. Say "the syntax accepts `X`", never where the
  rule was learned. Keep out code addresses, third-party build numbers, and the
  names of customer libraries, projects, or people.
- This project is unofficial. Use "SattLine" only to name the file format; do
  not imply affiliation with ABB.

## Code shape and complexity

Prefer splitting a module when the parts have different responsibilities. Do not
split a function only to lower a complexity number.

Two shapes stay deliberately long:

- A **grammar-production handler** in `transformer/` mirrors one production:
  each branch attaches one optional section in the order the grammar writes it.
  `base_picture_module`, `invocation_new_module`, `moduletype_definition`, and
  `sequence` are the largest. Moving a branch into a helper would scatter one
  production's assembly order across functions, so the handler stays whole.
- An **exhaustive dispatcher** over AST node types, such as `format_expr`,
  `format_seq_nodes`, `_emit_graph_object`, and `_emit_sfc_item`. Its branches
  are one line each, and a new node type must be added in one visible place.

The recursive helpers that used to carry a branch pile were split along their
real boundary instead: `_rebase_expression_spans` now separates span arithmetic,
literal rebuilding, container traversal, and dataclass rebuilding.

## AI-first documentation

This repository is maintained by AI agents. These conventions keep the
documentation usable as context:

- `AGENTS.md` is the short control plane: purpose, boundary, map, invariants,
  and workflow. It links to `docs/` for detail.
- `docs/README.md` is the index and the responsibility statement.
- Each document owns one subject and cross-links the others.
- Tables are preferred over prose for anything a future agent will look up:
  modules, flags, exit codes, rules, fields.
- Mermaid diagrams describe the graph that actually exists. If an import edge
  changes, update the diagram in the same change.
- Public behaviour changes update the matching document and add a changelog
  fragment.
- Do not duplicate a fact in three places. Link to the owner.

## AI workspace tooling

The repository ships its own OpenCode workspace:

| Path | Purpose |
| --- | --- |
| `.opencode/skills/sattline-parser/SKILL.md` | Repo map, invariants, recipes, verification ladder |
| `.opencode/commands/verify.md` | Full check ladder |
| `.opencode/commands/release.md` | Release checklist |
| `.opencode/commands/review.md` | Read-only review, run by the reviewer subagent |
| `.opencode/agents/parser-reviewer.md` | Read-only review subagent |
| `.github/pull_request_template.md` | PR checklist for boundary, tests, docs, and generated files |
| `scripts/check_docs.py` | Relative links, dash punctuation, Mermaid extraction |
| `.github/workflows/docs.yml` | Docs CI: links, prose, and Mermaid rendering |

`opencode.json` pins the Pyright LSP to Python files, formats Python with the
project Ruff, blocks direct edits to generated files, and asks before release
actions. The rules are guardrails, not a substitute for the instructions in
`AGENTS.md`.

## Public tree rule

This repository is public. Everything committed is visible to users and to
other agents.

- Describe what the syntax or tool does, not where the knowledge came from.
- Keep out customer names, internal paths, build numbers, and third-party
  binary details.
- A new data table needs a reproducible source: a fixture, a public manual, or
  a black-box check against the real tool.
- The `builtins/README.md` source list is the model to follow.

## Versioning and release

- Releases use calendar versioning: `YYYY.M.N`.
- The year and month name the month the release is published. A November
  release is `2026.11.N` even when it carries a breaking change; `N` increments
  within the month. `scripts/build_changelog.py --release` refuses a version
  whose year or month differs from the release date.
- The version orders releases; it is not a semantic-version compatibility
  contract.
- The public surface is the set of documented `__all__` lists, the `sattline`
  command, and its JSON schemas. [api.md](api.md) owns the exact list.
- Submodule paths not listed in [api.md](api.md) are internal and may change.
- A breaking change is marked in the changelog and lands in the release that
  makes it. There is no deprecation window and no compatibility shim.
- A superseded field, alias, or name is removed in the release that replaces it,
  so read the changelog before upgrading across a breaking entry.
- Adding a dataclass field is not breaking. Removing or renaming one is.

## Changelog

`CHANGELOG.md` follows Keep a Changelog and is assembled by
`scripts/build_changelog.py`; never edit its `[Unreleased]` section by hand.
Every pull request that changes user-visible behaviour adds one fragment file
named `changelog.d/<slug>.<type>.md`, where `type` is `added`, `changed`,
`removed`, `fixed`, or `security` and the content is the bullet text only.

A documentation change needs a fragment when it changes the public contract; a
pure clarification does not. `changelog.d/README.md` owns the naming rules and
the build commands, and CI runs `python scripts/build_changelog.py --check`.

## Dependency policy

Runtime dependencies are only:

- `lark[interegular]>=1.3.1,<1.4`
- `regex>=2023.12.25`

The parser does not call `regex` directly; Lark's regex engine does. The floor
is the first release with the Python 3.12 wheels used by CI, not a feature
requirement. CI tests both the locked minimum and the newest version that
satisfies the range.

Adding a runtime dependency is a design decision, not a convenience. Prefer the
standard library, then an existing dependency, then a new one.

## Checklist before a pull request

- [ ] The focused test passes.
- [ ] `pytest -q` passes.
- [ ] `python scripts/check_branch_coverage.py` passes.
- [ ] `ruff check src tests scripts benchmarks fuzzing` passes.
- [ ] `ruff format --check src tests scripts benchmarks fuzzing` passes.
- [ ] `pyright src tests benchmarks fuzzing scripts` passes.
- [ ] `bandit -q -r src fuzzing -x tests -c pyproject.toml` passes.
- [ ] `python scripts/check_docs.py` passes when Markdown changed.
- [ ] New syntax or rules have fixtures.
- [ ] New rules have golden expectations.
- [ ] New builtins update the catalogue source, not the generated file.
- [ ] `docs/` is updated.
- [ ] `changelog.d/` has a fragment for every user-visible change.
- [ ] `python scripts/build_changelog.py --check` passes.
- [ ] No consumer imports were added.
- [ ] No dash punctuation was added.
- [ ] No third-party identifiers were added.
