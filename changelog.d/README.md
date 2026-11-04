# Changelog fragments

Every pull request that changes user-visible behavior adds one file here. The
release step assembles the files into `CHANGELOG.md`, so two open PRs never
edit the same changelog lines.

## Naming

`<slug>.<type>.md`, where `slug` is lowercase words joined by hyphens and
`type` is one of the supported Keep a Changelog headings:

| Type | Heading |
| --- | --- |
| `added` | Added |
| `changed` | Changed |
| `removed` | Removed |
| `fixed` | Fixed |
| `security` | Security |

## Content

Write the bullet text only, in the same style as `CHANGELOG.md`. Do not add a
heading and do not edit the `[Unreleased]` section.

Example, `typed-tails.changed.md`:

```markdown
- **Typed tail nodes.** Tails are modelled as frozen dataclasses.
```

## Commands

```sh
python scripts/build_changelog.py --check
python scripts/build_changelog.py
python scripts/build_changelog.py --release 2026.12.0 --date 2026-12-01
```

`--check` validates the fragments and confirms `[Unreleased]` is empty. It
runs in CI. The plain invocation fills `[Unreleased]` for a preview. `--release`
moves the fragments under a dated version heading, reopens an empty
`[Unreleased]`, and deletes the consumed files.
