- **Project cache integrity.** The Lark parser cache now validates the
  per-user directory under the temporary directory as well as the `lark-cache`
  child, so a pre-created parent cannot be used to replace the signed cache
  entry. A symlinked cache directory now disables caching instead of being
  followed. The AST cache records the source snapshot taken before the parse,
  so a body edited while a worker was reading it is not stored as current, and
  a warm load no longer rewrites entries it read. A warm lookup resolves the
  cached base through the same case-insensitive index as a cold scan, so a
  dependency spelling whose case differs from the file name no longer falls
  through to a coarser extension.
