# Corpus Fixtures

Parser regression and fuzz-seeding corpus. All fixtures are SattLine sources (`.s`), grouped by expected behavior.

Layout:

- `valid/` for fixtures that must parse, transform, and produce a `BasePicture` cleanly
- `icf/` for the interactive control framework fixture program (also valid input)
- `invalid/` for sources that must fail strict validation (or at minimum not crash the parser)
- `edge_cases/` for high-risk semantics and parser corner cases

The fuzz harness consumes this directory via `collect_corpus_inputs` / `run_corpus_regression` in `src/sattline_parser/fuzz_harness.py`. Every file is re-parsed on each regression run, and the corpus seeds the `parser_fuzzer`.
