- **Cheaper parse hot paths.** The post-transform depth check caches a type's
  dataclass fields and checks atomic children against a tuple instead of a
  rebuilt union type, which halves its cost. The contextual lexer reads the
  compact-provenance flag once per run instead of once per token, so an
  uncompressed source skips the keyword retype entirely. `isinstance` checks
  across the parser, transformer, validator, and walker use tuples of types.
  Together these are about 9% of a cold parse.
