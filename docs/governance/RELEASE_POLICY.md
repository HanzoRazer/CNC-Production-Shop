# Release Policy

Status: Accepted
Order: CNC-RELEASE-POLICY-1
Date: 2026-08-24

## Purpose

Define the governed release lifecycle for the installable distribution:

```text
cnc-production-shop
```

This policy answers when `[project].version` changes, what a release number
means, how tags are named, what a releasable artifact is, how release notes
are produced, how subsystem API versions relate to distribution releases, and
what evidence is required before a release can be declared complete.

It does **not** authorize a production release, a GitHub Release, or
publication to PyPI or any other index.

Version *authority* lives in `VERSIONING_POLICY.md`. Release *lifecycle*
lives here.

## Definitions

### Distribution version

The version of the `cnc-production-shop` wheel, declared by
`[project].version` in `pyproject.toml`.

### Release

A completed, evidenced distribution event. A Git tag alone is not a release.

### Release identifier

```text
REL-CNC-<VERSION>
```

Example: `REL-CNC-0.2.0`. Identity is keyed to the distribution version.

### Canonical release tag

```text
vMAJOR.MINOR.PATCH
```

Example: `v0.1.1`. Only this form is a distribution release tag.

### Historical / governance witness tag

Any other Git tag with documented provenance. These are not distribution
releases. The existing witness:

```text
msme-001-foundation-original
```

is preserved. Do not rewrite or delete it. Release-readiness ignores it when
deciding whether a proposed `v*` tag already exists.

### Artifact

The installable wheel:

```text
cnc_production_shop-<version>-py3-none-any.whl
```

A future source distribution, if added, would be:

```text
cnc_production_shop-<version>.tar.gz
```

Every artifact record must carry a SHA-256 digest (`sha256:` + 64 hex).

## Version Authority

`[project].version` is the single distribution version. Packaged
`__version__` attributes resolve to that value via `cnc_version`.

Subsystem API versions such as `MSME_API_VERSION` remain independently
named. Schema versions, quote revisions, and artifact revisions remain
independent.

Do not infer the distribution version from commit count, branch name, or
SCM metadata.

## Semantic Version Rules

Use `MAJOR.MINOR.PATCH`. The project is pre-1.0, so current releases follow
`0.MINOR.PATCH`.

| Component | Meaning |
|---|---|
| PATCH | Backward-compatible defect fix or packaging correction |
| MINOR | New backward-compatible product capability or materially expanded public API |
| MAJOR | Reserved for post-1.0 incompatible release policy |

While `<1.0`, a public incompatibility increments MINOR, resets PATCH to 0,
and must be documented as compatibility-affecting. Do not silently treat a
breaking change as a patch.

Examples:

```text
0.1.0 → 0.1.1    patch
0.1.1 → 0.2.0    minor
0.2.3 → 0.3.0    breaking change before 1.0
```

A distribution release may include no MSME API change. An MSME API change
may require a distribution release, but the two numbers need not match.
Release notes must report both when MSME changes.

## Release Eligibility

A source tree is internally consistent for a proposed version only when:

- `[project].version` parses as `MAJOR.MINOR.PATCH` with no `v` prefix
- the proposed version equals `[project].version` in that tree
- every feature package exists under the tree and binds `__version__` to
  `cnc_version.distribution_version()` (not a hardcoded literal)
- `MSME_API_VERSION` is independently readable from that tree
- git metadata is present and the working tree is clean
- the canonical tag `v<version>` does not already exist in that tree
- `CHANGELOG.md` has a section for that version, or release-ready
  `Unreleased` material (a governed category heading with at least one entry)
- if a wheel is supplied, its filename and metadata match the version

`scripts/release/check_release_readiness.py` evaluates these checks against
`--root` only and writes nothing. It does not consult the caller's installed
distribution or imported packages. `--root` defaults to this checkout.

Eligibility is not a release.

## Release States

```text
development
release_candidate
released
withdrawn
```

### `development`

Normal branch state. No canonical release tag. The current project version
may be a declaration only (as `0.1.0` is today).

### `release_candidate`

Version selected and evidence assembled. Canonical release not yet
published.

### `released`

Canonical `v*` tag and approved artifact exist with complete evidence.

### `withdrawn`

The release remains historically recorded but must no longer be recommended
for use. Do not delete history as a substitute for withdrawal.

## Tag Policy

Canonical distribution tags:

```text
v0.1.0
v0.1.1
v0.2.0
```

Do not use `release-0.1.0`, `cnc-v0.1.0`, or `prod-0.1.0` as canonical
distribution tags.

Subsystem API versions must not create distribution-like Git tags.

Witness tags remain outside this namespace.

This sprint creates no real `v*` tag.

## Artifact Policy

Canonical wheel name:

```text
cnc_production_shop-<version>-py3-none-any.whl
```

The release manifest must record SHA-256. An artifact record without a
cryptographic hash is invalid.

Editable-install success is not evidence that the wheel is valid.

## Release Notes

`CHANGELOG.md` is release-oriented. Commit history is not the changelog.
PR descriptions are evidence, not release notes.

Categories are defined in `CHANGELOG_POLICY.md`.

`scripts/release/render_release_notes.py` emits deterministic Markdown from
governed inputs. It does not post anywhere.

## Subsystem API Versions

Report independently. Example:

```text
cnc-production-shop distribution: 0.1.0
MSME_API_VERSION:                0.2.0
```

## Schema Versions

`BidV1`, `ProposalV1`, instrument-profile `schema_version`, and related
schema names remain independently versioned. They do not inherit the
distribution version.

## Release Evidence

A release requires all of:

```text
version authority updated
clean commit
full tests green
supported Python CI green (3.11 / 3.12)
wheel builds
wheel installs
artifact metadata matches source
release notes exist
tag points to the verified release commit
post-tag verification succeeds
```

Evidence is recorded in a `ReleaseManifestV1` (`schemas/releases/`).

If any item is absent: `RELEASED: no`.

## Withdrawal / Supersession

Withdraw by recording `release_state: withdrawn` on the existing
`REL-CNC-<VERSION>` identity. Keep the tag and notes. Recommend a later
version for use.

## Publication

Default posture: **internal-only**.

A later execution order (`CNC-RELEASE-EXECUTION-1`) must explicitly
authorize each of:

- GitHub Release creation
- artifact upload
- PyPI or any package-index publication

Until that authorization exists, do not publish.

## Prohibited Practices

- Publishing to PyPI or an internal index from this policy sprint
- Creating a real production `v*` tag to test tooling
- Creating GitHub Releases automatically
- Deriving versions from Git history or commit count
- Introducing setuptools-scm, semantic-release, or commitizen
- Treating `msme-001-foundation-original` as a distribution release
- Backfilling a dated `0.1.0` changelog section without release evidence
- Mutating `pyproject.toml` from a release script
- Silent fallback versions (`0.0.0`)
- Deleting release history instead of withdrawing

## Examples

Current tree (not a completed release):

```text
distribution version declaration: 0.1.0
canonical tag:                    absent
CHANGELOG:                        Unreleased only
RELEASED:                         no
```

A future patch release, once authorized and evidenced:

```text
REL-CNC-0.1.1
tag: v0.1.1
wheel: cnc_production_shop-0.1.1-py3-none-any.whl
state: released
```

Follow-on:

```text
CNC-RELEASE-EXECUTION-1
```

perform the first governed release only after this policy is merged.
