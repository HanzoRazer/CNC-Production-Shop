# Versioning Policy

Status: Accepted
Order: CNC-VERSION-POLICY-1
Date: 2026-08-23

## Purpose

This repository produces one installable Python distribution. Subsystems may
mature on their own schedule. Those two facts must not be expressed by the
same number.

This policy answers permanently:

- What `__version__` means when a Python package is shipped inside the
  `cnc-production-shop` wheel.
- How a subsystem such as the Musical Spatial Mapping Engine (MSME) expresses
  independent API maturity without appearing to be a separately distributed
  package.

It does not authorize a release, a tag, or a PyPI publication.

## Definitions

### Distribution version

The version of the installable wheel:

```text
cnc-production-shop
```

Declared by `[project].version` in `pyproject.toml`. Reported at runtime by
`importlib.metadata.version("cnc-production-shop")`.

### Subsystem API version

The version of a governed internal public contract. The only named subsystem
API version today is:

```text
musical_spatial_mapping.MSME_API_VERSION
```

It describes MSME's public API and behavioral contract. It is not a
distribution version and does not imply a separately installable package.

### Schema version

JSON and business schemas remain independently versioned under their own
governance. Examples: `BidV1`, `ProposalV1`, `MachineProfileV1`,
`QuotePackageV1`, instrument-profile `schema_version`.

Do not conflate:

```text
distribution version
API version
schema version
quote revision
artifact revision
```

They solve different problems.

## Distribution Version

The canonical installed artifact is `cnc-production-shop`.

`[project].version` in `pyproject.toml` is the single authority for that
artifact. There is exactly one project distribution version. It is not
generated from Git, commit counts, environment variables, or a network lookup.

Current value: `0.1.0`.

MSME reaching API maturity `0.2.0` does not mean the complete CNC Production
Shop distribution has reached release `0.2.0`. Do not manufacture a
repository-wide release merely to eliminate a naming ambiguity.

## Subsystem API Version

MSME retains independent maturity under an explicit name:

```python
MSME_API_VERSION = "0.2.0"
```

Meaning: version of the public Musical Spatial Mapping Engine API and
behavioral contract.

It does **not** represent a separately installable distribution. MSME is
currently shipped as a subpackage of `cnc-production-shop`.

## Authority

| Question | Authority |
|---|---|
| What version is the installed wheel? | `[project].version` / `importlib.metadata` |
| What does `package.__version__` mean? | The containing `cnc-production-shop` distribution |
| What is MSME's public contract maturity? | `MSME_API_VERSION` |
| What is a JSON/business schema revision? | That schema's own version field or `V1` name |

`musical_spatial_mapping.__version__` previously held `0.2.0` because that
value described MSME API maturity. That overloaded `__version__`. The
distribution version is now authoritative for `__version__`. MSME's prior
information is preserved as `MSME_API_VERSION`.

This is an authorized contract clarification: the package is still alpha, and
the previous value never described a separately shipped distribution.

## Runtime Reporting

Preferred installed-runtime mechanism:

```python
from importlib.metadata import PackageNotFoundError, version

version("cnc-production-shop")
```

Target public semantics:

```python
import musical_spatial_mapping as msme

msme.__version__
# version of the installed cnc-production-shop distribution

msme.MSME_API_VERSION
# version of the MSME public API/behavioral contract
```

Installed metadata must satisfy:

```text
importlib.metadata.version("cnc-production-shop")
==
musical_spatial_mapping.__version__
```

These are distinct intentionally:

```text
Distribution version = packaging/release lifecycle
MSME API version      = subsystem contract lifecycle
```

## Source Checkout Behavior

Installed-wheel behavior is authoritative.

When the distribution is not installed (a source checkout with no metadata):

1. Ask `importlib.metadata` for `cnc-production-shop`.
2. If unavailable, read `[project].version` from this repository's
   `pyproject.toml` using the standard-library `tomllib`.

The fallback must be deterministic. It must not introduce a third independently
maintained version string.

If neither installed metadata nor readable project metadata is available, fail
explicitly. Do not return `"0.0.0"`, `"unknown"`, or any other fabricated
sentinel.

Implementation: `cnc_version.distribution_version()`. The helper is a
neutral packaged module so no feature package owns the authority and MSME
does not depend on `business`.

## Compatibility

Changing `musical_spatial_mapping.__version__` from `0.2.0` to the
distribution version (`0.1.0` today) changes the meaning of that attribute.

Documented here so the change is not silent. Callers that need MSME contract
maturity must read `MSME_API_VERSION`.

## Version Bump Rules

### Distribution version changes when

Examples:

- a CNC Production Shop release is cut
- distribution-level public APIs change
- packaging/release authority decides a new release

Use Semantic Versioning while pre-1.0: `0.MINOR.PATCH`.

No automatic bump is implied by a subsystem API change.

### MSME API version changes when

Examples:

- public MSME models change
- public enums change incompatibly
- facade signature changes
- serialization contract changes
- golden behavioral contract changes intentionally

Internal refactoring does not automatically require an MSME API bump.

### Schema versions remain independent

`BidV1`, `ProposalV1`, `MachineProfileV1`, `QuotePackageV1`, and MSME
instrument-profile `schema_version` must not inherit the repository
distribution version.

## Prohibited Patterns

Do not:

- set `package.__version__` to an independent subsystem number when that
  package is not independently distributed
- duplicate the project-version literal inside a subpackage as a fallback
- read the version from a Git branch name or commit count
- look up the version over the network
- mutate the version per environment
- silently fall back to `"0.0.0"`
- introduce setuptools-scm, hatch-vcs, bump2version, commitizen, or
  semantic-release as part of ordinary version reporting

Those release-automation tools belong to a later `CNC-RELEASE-POLICY-1`
evaluation. They are out of scope here.

## Examples

After this policy:

```text
Distribution: 0.1.0
MSME API:      0.2.0
```

```python
import importlib.metadata
import musical_spatial_mapping as msme

assert msme.__version__ == importlib.metadata.version("cnc-production-shop")
assert msme.MSME_API_VERSION == "0.2.0"
```

A later distribution release to `0.2.0` would make the two numbers coincide
without changing what either name means.

## Version inventory

Classified so a string containing "version" is not rewritten automatically.

| Location | Current value | Class |
|---|---|---|
| `pyproject.toml` `[project].version` | `0.1.0` | distribution authority |
| `cnc_version.distribution_version()` | runtime resolver | distribution authority |
| seven packaged `__version__` attributes | distribution version | distribution (resolved at runtime) |
| `musical_spatial_mapping.MSME_API_VERSION` | `0.2.0` | subsystem API |
| instrument-profile `schema_version` | `1.0` | schema |
| `BidV1` / `ProposalV1` / `BidSummaryV1` / related | `V1` in the type name | schema |
| `tests/golden/msme_v1_vectors.json` | artifact name | behavioral spec / artifact revision |
| `python_version` / Ruff `target-version` | `3.11` | tooling, not a product version |

### Package alignment

`CNC-VERSION-ALIGNMENT-2` migration complete.

All package-level `__version__` attributes shipped inside
`cnc-production-shop` report the containing distribution version.

The seven feature packages resolve `__version__` from the neutral
`cnc_version.distribution_version()` helper. That helper has no CAM, business,
or MSME dependency. No feature package owns a duplicated distribution-version
literal.

`cnc_version` itself does not expose `__version__`; it is the resolver, not a
feature surface.

Follow-on:

```text
CNC-RELEASE-POLICY-1
```

Mission: define release numbering, when `[project].version` changes, tag
conventions, changelog authority, and whether automated bumping or artifact
publication is warranted. Do not begin release automation until version
authority is fully aligned and enforced.
