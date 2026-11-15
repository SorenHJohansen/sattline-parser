- **SARIF output for code scanning.** `sattline check --sarif` and
  `sattline project --sarif` emit a SARIF 2.1.0 log. A validation finding uses
  its `SL-V###` id as the SARIF rule id and the registry supplies the rule
  descriptor; a parse, decode, project, or read finding keeps its own id. Each
  result carries the severity and, when the finding has one, a file location.
  `--sarif` is exclusive with `--json` and `--jsonl`.
