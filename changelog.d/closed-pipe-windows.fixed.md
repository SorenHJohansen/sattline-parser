- **Closed output pipe on Windows.** A consumer that closes the pipe now stops
  the report with the content exit code instead of reporting an internal error,
  because the Windows `EINVAL` spelling of a closed stream is handled.
