# Changelog Policy

Status: Accepted
Order: CNC-RELEASE-POLICY-1
Date: 2026-08-24

## Purpose

Govern how `CHANGELOG.md` records distribution-oriented change.

```text
CHANGELOG is release-oriented
commit history is not the changelog
PR descriptions are evidence, not release notes
```

## Structure

Keep a Changelog-style headings without depending on that project.

```markdown
# Changelog

## Unreleased

### Added
- …

## [0.1.1]
```

Do not invent historical releases or dates. The current project version
`0.1.0` is a version declaration, not proof of a completed release. Until a
governed release exists, the file holds `# Changelog` and `## Unreleased`
only.

## Categories

Use only these category headings, in this order when several appear:

```text
Added
Changed
Fixed
Deprecated
Removed
Security
Packaging
Governance
```

Omit a category when it has no entries. Do not invent empty sections in
rendered release notes.

## Unreleased vs released

Work accumulates under `## Unreleased`.

A release execution order freezes Unreleased material into a version
section. That freeze is a release-execution act, not this policy sprint.

Release-ready Unreleased material means: at least one of the governed
category headings exists under Unreleased and contains at least one list
entry.

## Subsystem API versions

When MSME's public contract changes, the changelog entry must name
`MSME_API_VERSION`. The distribution version and the MSME API version may
differ.

Schema versions are not changelog substitutes.

## Authority

`CHANGELOG.md` is the release-note source. Rendered notes must not add
claims that are absent from the changelog or the release manifest.
