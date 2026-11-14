- **`sattline project` caches by default.** A load writes and reads the parser
  caches under `$XDG_CACHE_HOME/sattline-parser/project` unless `--no-cache` is
  given; `--cache-dir` overrides the location. A repeated load of an unchanged
  tree skips parsing and takes 75s instead of 224s on the same 267-program tree.
  The directory holds parsed ASTs of the loaded sources and must stay private.
