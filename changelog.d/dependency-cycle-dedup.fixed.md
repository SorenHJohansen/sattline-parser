- **Dependency cycle identity.** Cycles are deduplicated by directed node
  sequence, so `a -> b -> c -> a` and `a -> c -> b -> a` both appear. Rotations
  of the same cycle still collapse, and the CLI reports the real edge order.
