- **`sattline check --rule` only accepts ids that command can produce.**
  `PARSE_ERROR` and `DECODE_ERROR` remain valid, and a synthetic id that belongs
  to another command, such as `READ_ERROR`, is now a usage error instead of a
  filter that silently matched nothing.
