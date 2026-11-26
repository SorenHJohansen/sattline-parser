- **Project-layer loading work.** An uncached load no longer takes a SHA-256
  snapshot of every source file, and a file that fails to parse is never
  hashed. Dependency closures are memoized, an acyclic module-type graph is
  cleared by one global cycle search, the planner uses a FIFO deque instead of
  shifting a list, and the project symbol index fills definitions and usages
  from one AST walk.
- **Project-loading benchmarks.** Generated deep, wide, diamond, and
  module-type graphs, plus uncached, cold-cache, and warm-cache loads, now have
  benchmark coverage.
