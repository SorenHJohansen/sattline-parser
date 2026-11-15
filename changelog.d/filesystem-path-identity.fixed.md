- **Lookup roots compare as filesystem paths.** Two configured roots that differ
  only in letter case are two roots on a case-sensitive filesystem, so a root
  such as `Library` is no longer collapsed into `library`. Windows path
  comparison stays case-insensitive. Identifier comparison is unchanged and
  still uses the case-folding name table.
