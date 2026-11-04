---
name: SattLine Parser
description: Work in the sattline-parser repository. Use for parser, AST, transformer, validation, project-layer, CLI, fixture, or documentation changes in this repo.
---

# SattLine Parser

`src/sattline_parser` is language infrastructure for the SattLine PLC language.
It answers "what is in this source, and how is it structured?". It does not
analyse, score, refactor, or generate programs.

## First read

1. `AGENTS.md` for the control plane and invariants.
2. `docs/README.md` for the responsibility boundary and index.
3. The owning document for the subsystem you are changing.

Do not read the whole `docs/` tree up front. Load the matching document.

## Map

| Area | Path | Public entry |
| --- | --- | --- |
| Grammar and lexer | `src/sattline_parser/grammar/` | `create_parser` |
| Source decoding | `src/sattline_parser/preprocessing/` | `preprocess_source` |
| Source provenance | `src/sattline_parser/source_document.py` | `SourceDocument` |
| Parse pipeline | `src/sattline_parser/source_io.py` | `parse_source_file`, `parse_source_text` |
| AST models | `src/sattline_parser/models/` | `BasePicture`, expression nodes |
| Transformer | `src/sattline_parser/transformer/` | `SLTransformer` |
| Syntax diagnostics | `src/sattline_parser/errors.py` | `describe_parse_error` |
| Validation | `src/sattline_parser/validation/` | `validate_basepicture` |
| Builtin facts | `src/sattline_parser/builtins/` | signatures and record specs |
| Project layer | `src/sattline_parser/project/` | `SattLineProject.load` |
| CLI | `src/sattline_parser/cli/` | `sattline` command |
| Docs | `docs/` | `docs/README.md` |

## Where to change what

| Change | Owning file or directory |
| --- | --- |
| New syntax | `grammar/sattline.lark`, `grammar/constants.py` |
| Keyword spelling or case folding | `grammar/constants.py`, `grammar/keywords.py` |
| Comment handling | `grammar/sattline_lexer.py` |
| Coded stream or marker decoding | `preprocessing/` |
| Original-source position mapping | `source_document.py` |
| Parse orchestration | `source_io.py` |
| AST field or node | `models/` |
| Tree construction | `transformer/` mixins |
| Parse-error sentence | `errors.py` |
| Validation rule | `validation/` |
| Discovery, formats, loading, caches | `project/` |
| Graphics companion parsing | `project/graphics_parsing.py`, `project/graphics_bindings.py` |
| CLI command | `cli/cmds/` |
| Builtin signature or record field | `scripts/builtin_catalogue_source.json`, `builtins/records.py` |
| Documentation | `docs/` |

## Invariants

- Strict, no silent fallback. Unknown compressed markers raise
  `PreprocessError`. A failed parse raises. A skipped project program is
  recorded as a diagnostic.
- Every span and diagnostic points into the original source, even after
  decoding.
- `grammar/sattline.lark` is the only grammar.
- Never import a consumer tool. The package ships standalone on PyPI.
- Never edit `src/sattline_parser/builtins/catalogue.json` by hand. Edit
  `scripts/builtin_catalogue_source.json` and run the generator.
- Keep Python files Pyright strict-clean.
- No deprecation windows and no compatibility shims. Remove a superseded field,
  alias, or name in the same breaking release. Bump a cache version and discard
  old entries instead of reading an older shape.
- Update `docs/` with the behaviour it describes.
- Never commit directly to `main`. Use a branch and a pull request.
- Record behaviour, not origin. Keep third-party names and build details out
  of the public tree.

## Verification ladder

Use `.venv/bin/python` when the virtual environment exists. Otherwise use
`uv run`.

```bash
# 1. The focused check for the file or subsystem you changed
.venv/bin/python -m pytest tests/parser/test_parser_core_grammar.py -q

# 2. Lint and format
.venv/bin/python -m ruff check src tests scripts benchmarks
.venv/bin/python -m ruff format --check src tests scripts benchmarks

# 3. Types
.venv/bin/pyright src tests benchmarks

# 4. Security
.venv/bin/python -m bandit -q -r src -x tests -c pyproject.toml

# 5. Full suite plus both coverage gates
.venv/bin/python scripts/check_branch_coverage.py

# 6. Benchmarks
.venv/bin/python -m pytest benchmarks --no-cov -q

# 7. Documentation checks when Markdown changed
.venv/bin/python scripts/check_docs.py
```

The coverage script runs the full suite, so step 5 already proves the suite
passes. Report each command and its result. If a check fails, stop and report
the failure before making more edits.

The `/verify` command runs this ladder. The `/review` command runs a read-only
review. The `/release` command runs the release checklist.

## Recipes

### Add a validation rule

1. Prove the rule with a fixture, a public manual, or a black-box check. A
   plausible rule without evidence is a bug. See `RETIRED_CODES` in
   `validation/rules.py`.
2. Add a `DiagnosticCode` member.
3. Add the matching `Rule` to `validation/rules.py` with its summary, scope,
   and status.
4. Put the rule in the owning module: declarations in `declarations.py`, code
   and SFC in `code.py`, type facts in `typing.py`, transfers in `transfers.py`.
5. Emit a `Diagnostic` with a sentence and a `span`.
6. Add a fixture under `tests/fixtures/corpus/invalid/` or `edge_cases/`.
7. Add the golden expectation to `tests/fixtures/validation/expectations.json`.
8. Add a focused test.
9. Update `docs/validation.md` and run `python scripts/gen_rule_table.py`.

### Add a grammar form

1. Add the rule to `grammar/sattline.lark`.
2. Add constants to `grammar/constants.py` when the rule needs a spelling.
3. Add the AST field to `models/`.
4. Add the transformer method to the owning mixin.
5. Add a corpus fixture.
6. Add a test that asserts the constructed shape.
7. Update `docs/grammar.md`, `docs/ast.md`, and `docs/transformer.md`.

### Add a corpus fixture

- `valid/` must parse, transform, and validate cleanly.
- `invalid/` must fail strict validation, or at minimum fail safely.
- `edge_cases/` covers high-risk semantics and parser corners.

Then add the expectation and run the corpus test and the fuzz regression.

### Regenerate builtins

```bash
# Edit the authored source, never the generated catalogue
$EDITOR scripts/builtin_catalogue_source.json
.venv/bin/python scripts/gen_builtin_catalogue.py
.venv/bin/python scripts/gen_builtin_catalogue.py --check
```

Add a fixture and a test for the new arity or argument behaviour. Update
`docs/builtins.md` when counts or provenance rules change.

### Add a CLI command

1. Add `cli/cmds/<name>.py` with `register` and `run`.
2. Register it in `cli/__init__.py`.
3. Reuse `_common.py`, `_findings.py`, `_io.py`, and `_json.py`. Do not add
   parsing or validation logic to the CLI.
4. Add CLI tests for output, exit code, and refusal rules.
5. Update `docs/cli.md` and the schema list in `cli/cmds/version.py`.

## Useful commands

```bash
# Parse one file without validation
sattline parse program.s --tree --depth 3

# Parse and validate
sattline check program.s --jsonl

# Load a project tree
sattline project programs/ libs/ --targets MyProgram --json

# Query one structural question
sattline query program.s --what writers --name Counter

# Regenerate the builtin catalogue and verify it
python scripts/gen_builtin_catalogue.py
python scripts/gen_builtin_catalogue.py --check

# Check documentation links, prose, and Mermaid extraction
python scripts/check_docs.py --mermaid-dir /tmp/sattline-mermaid
```

## Do not

- Do not add analysis, lint policy, metrics, refactoring, or code generation.
- Do not import a consumer tool or add a runtime dependency without a design
  decision.
- Do not silently widen validation or parsing fallbacks.
- Do not edit generated files, build outputs, coverage reports, or `uv.lock` by
  hand.
- Do not commit, push, tag, merge, or publish without explicit permission for
  that action.
