- **Three reserved rules retired.** `DIVISION_BY_ZERO` is disproved by the
  corpus (a valid unit divides by a literal zero, which is runtime semantics),
  and `SEQUENCE_TRANSITION_AFTER_TRANSITION` and `PARALLEL_BRANCH_INCOMPLETE`
  are already covered by the sequence position rules. They are listed by
  `sattline rules --include-retired` as retired.
