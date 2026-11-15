- **`corpus --jobs` uses processes.** Each job is independent and returns only
  counts, so the scan now runs in a process pool shaped by the same start-method
  rule as the project loader rather than sharing one cached Lark parser across
  threads. Order and output are unchanged. A pool that cannot start, or one
  whose worker dies, falls back to scanning in this process with a warning.
