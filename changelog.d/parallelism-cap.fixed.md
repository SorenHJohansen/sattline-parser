- **Bounded process and thread counts.** `sattline project --workers` accepts
  1 to 32 and `sattline corpus --jobs` accepts 1 to 32; a larger value is a
  usage error instead of a request that can exhaust the machine.
