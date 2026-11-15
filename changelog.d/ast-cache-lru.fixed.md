- **AST cache eviction follows last use.** A successful load touches its entry,
  the cap is configurable through `FileASTCache(max_entries=...)`, and a
  symlinked entry is ignored instead of read.
