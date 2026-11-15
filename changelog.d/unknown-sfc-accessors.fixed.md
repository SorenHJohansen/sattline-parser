- **Unknown SFC accessors are reported.** Only the runtime field names an
  element kind exposes are treated as accessors: `X`, `Hold`, `Reset`, and `T`
  for a step, and `Hold` and `Reset` for a sequence. A suffix such as
  `Step.Foo`, or `Sequence.X`, is now an undefined reference instead of an
  unchecked dotted name. Availability still comes from `SeqControl` and
  `SeqTimer`, which `SL-V051` reports separately.
