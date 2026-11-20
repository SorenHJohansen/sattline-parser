# Security Policy

## Supported versions

Only the latest published release receives security fixes. Older releases are
not patched, so upgrade to the newest version on PyPI before reporting.

## Reporting a vulnerability

Report privately through GitHub's private vulnerability reporting:

https://github.com/SorenHJohansen/sattline-parser/security/advisories/new

Do not open a public issue for a suspected vulnerability. A useful report
includes:

- the package version (`sattline version --json` or `pip show sattline-parser`),
- the smallest input that triggers the problem, as a `.s` file or an inline
  snippet,
- the Python version and platform,
- what happened, and what you expected instead.

You can expect an acknowledgement, an assessment of impact, and either a fix or
a documented decision not to fix. This is a single-maintainer project, so
timelines are best effort.

## Scope

The parser processes untrusted source text. In scope:

- crashes, hangs, or unbounded memory use triggered by input, in the parser,
  the decoders, the validator, or the project loader
- regular expression denial of service in the grammar or the decoders
- path traversal or unintended file access in the project layer and the CLI
- weaknesses in the published package or its release workflow

The parser-owned caches are an optimisation and are treated as private to one
user. A cache directory that cannot be proven private (owner, mode, parent
chain, or Windows security descriptor) is disabled instead of used, and a
directory replaced after it was opened is refused. A cache in a location another
user can write is outside this boundary, so do not point `cache_dir` at a shared
location. Reports that require write access to the user's own private cache
directory are out of scope.

Out of scope:

- parse or validation results that are merely wrong. These do not crash or
  hang, so report them as normal issues with a fixture
- vulnerabilities in `lark`, `regex`, or another dependency. Report those
  upstream, though a note here is welcome if a version constraint needs to
  change
