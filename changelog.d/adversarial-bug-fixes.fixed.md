- **Adversarial fixes.** IDE text rendering scans the source once instead of
  rescanning the remainder of every long line, a step fork is written after its
  code blocks, and numeric literal metadata is detached from the caller across
  the project boundary and emitted as plain numbers by the serializer.
- **Hostile input handling.** A symlink-loop root, a 254-byte unit name, and
  an unreadable corpus directory now map onto the documented load or usage
  errors. A replaced lookup-cache root is no longer written into, and a cycle
  between `Straße` and `STRASSE` keeps both units distinguishable.
- **CLI output contract.** A short report that fails only on the final flush
  exits 2 instead of 120, output failures such as a full device exit 2, JSON
  stays valid on an ASCII stream, a non-UTF-8 filename yields a valid SARIF
  URI, and an empty `--stdin-name` is refused.
- **Literal and range edges.** A very long integer literal clamps instead of
  raising, negative ranges clamp to the mapped start, and comment continuation
  lines can break at spaces.
