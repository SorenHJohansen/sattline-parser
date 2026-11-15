- **Worker parse failures keep their cause.** A body parsed in a worker now
  rebuilds the same exception type and source position in the parent, so a
  broken dependency has the same `__cause__` at any worker count.
