- **The AST cache identifies a source by its bytes.** An entry records the
  SHA-256 of the exact bytes that were parsed. The `mtime_ns` and `size` stat
  snapshot is only a cheap first filter, so an edit that keeps the file size and
  lands inside the filesystem's mtime granularity, or a restore that puts an old
  mtime back, is a miss and the body is reparsed. `FILE_AST_CACHE_VERSION` is
  `11`, and entries from an older version are discarded.
