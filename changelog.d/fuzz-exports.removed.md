- **Fuzz exports leave the package.** `FuzzResult`, `assert_no_crashes`,
  `assert_no_timeouts`, `collect_corpus_inputs`, `fuzz_harness`,
  `fuzz_parse_text`, `generate_random_text`, `run_corpus_regression`, and
  `run_random_fuzz` are no longer attributes of `sattline_parser`. The harness
  is repository-local under `fuzzing/` and was never shipped in the wheel.
