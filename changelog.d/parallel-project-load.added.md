- **Parallel project load.** `SattLineProject.load(..., workers=N)` parses
  program bodies in `N` processes, and `sattline project` gains `--workers`
  defaulting to `min(8, cpu_count)`. Discovery resolves the whole closure first,
  so every plan is independent and the result is identical at any worker count:
  a 268-program library tree that takes 255s in one process splits across
  workers without changing the result. The library default stays `workers=1`. A single-threaded caller forks;
  a caller with other threads gets `forkserver`, because forking a threaded
  process is deprecated and can inherit a held lock. A daemonic parent, or a
  pool that cannot start, parses in the calling process instead of failing the
  load.
