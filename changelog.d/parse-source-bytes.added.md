- **`parse_source_bytes`.** Parses source bytes the caller already read, with the
  same decoding and provenance as `parse_source_file`, and keeps the bytes that
  were parsed in the caller's hands. The project cache uses it to record a
  digest of exactly the revision it stored.
