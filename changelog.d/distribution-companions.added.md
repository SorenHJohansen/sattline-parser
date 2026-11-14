- **Distribution companions.** The project layer now resolves and parses the
  distribution companion (`.p` draft, `.q` official) beside the selected code
  body. `SattLineProgram` gains `distribution_path`, `distribution`, and
  `has_executing_system`, the last being `None` when no companion was found,
  `False` when the executing-system list is empty, and `True` when it is not.
  `parse_distribution_file`, `parse_distribution_text`,
  `resolve_distribution_companion_path`, `DistributionData`, and
  `DistributionTarget` are public. `sattline project` reports the answer in both
  its text and JSON output, and the JSON program rows gain `distribution`,
  `has_executing_system`, and `executing_systems`. A companion that exists but
  does not parse is a load
  failure, never an empty list, and `check`, `parse`, `query`, `decode`, and
  `diff` refuse a `.p`/`.q` input as a companion rather than reporting it
  as broken source.
