- **`sattline project --graph` reports validation findings.** Graph mode prints
  the validation rows and includes them in its JSON payload, so a run no longer
  exits `1` on a finding it did not show. `--of` with a name outside the loaded
  graph is a `PROJECT_QUERY_ERROR` finding instead of an empty graph.
