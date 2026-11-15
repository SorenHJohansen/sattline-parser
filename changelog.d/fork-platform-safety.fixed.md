- **The parse pool no longer forces `fork` on every Linux host.** `fork` is
  used only on Linux before Python 3.14 with no other Python thread, and the
  platform default applies on macOS and newer Linux runtimes.
