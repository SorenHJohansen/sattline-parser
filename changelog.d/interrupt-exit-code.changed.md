- **Ctrl-C exits `130`.** An interrupted command now returns the shell
  convention of 128 + SIGINT instead of the usage code `2`, so a script can tell
  a cancelled run from a bad invocation.
