- **`sattline project` caches by default.** A load writes and reads the parser
  caches under `$XDG_CACHE_HOME/sattline-parser/project` unless `--no-cache` is
  given; `--cache-dir` overrides the location. A repeated load of an unchanged
  tree skips parsing: 68s instead of 255s on a 268-program tree. Workers read the
  cache and the parent writes it, so the per-user key stays single-process. The
  directory holds parsed ASTs of the loaded sources and must stay private.
