- **An unreadable project root is an input error, not an internal error.**
  `sattline project` exits `2` with `cannot read ...` instead of exiting `3` on a
  `PermissionError`, and the library raises `ProjectLoadError` rather than
  letting the `OSError` escape.
