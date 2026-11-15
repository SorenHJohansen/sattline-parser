- **A falsy parameter mapping literal is kept.** `Name => False` was stored as
  no literal at all, because the optional `GLOBAL` keyword was detected with a
  boolean type test and the literal source was consumed as the absent keyword.
  The keyword is now detected by identity, so `False`, `0`, and `""` reach the
  model as the values they are.
