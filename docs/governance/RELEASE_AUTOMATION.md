# Release Candidate Automation

Status: Accepted
Order: CNC-RELEASE-AUTOMATION-1
Date: 2026-08-25

## Purpose

Automate the mechanical portions of the governed
`cnc-production-shop` release process **after** a human has already
selected a version and prepared the source tree.

This is not an unattended deployment system.

## Authority boundary

```text
version selection        = human decision
release authorization    = human decision
external publication     = human decision
tag creation             = gated action
artifact verification    = automated
manifest generation      = automated
hash generation          = automated
release readiness        = automated
```

Release candidate verification may be automated. Release identity, tag
authorization, and external publication remain governed manual
decisions.

## What the workflow does

GitHub Actions workflow:

```text
.github/workflows/release_candidate.yml
```

Name: `Release Candidate Verification`.

It is invoked only by `workflow_dispatch`. A human supplies:

```text
version            (required)   e.g. 0.1.2
expected_commit    (optional)   40-character SHA that HEAD must match
release_state      (optional)   must remain release_candidate
```

The workflow then:

1. Checks out the selected ref, including tags.
2. Runs on Python 3.11 and 3.12.
3. Runs ruff, mypy, pytest, and repository validators.
4. Builds the wheel.
5. Inspects the wheel (filename, METADATA, duplicate members, packages,
   MSME resources, SHA-256).
6. Installs the wheel into a fresh virtualenv outside the checkout.
7. Verifies site-packages imports, package version parity,
   `MSME_API_VERSION`, packaged resources, MSME CLI, and `cam-assist`.
8. Generates a `release_candidate` manifest and validates it.
9. Writes a human-readable evidence report.
10. Uploads those files as GitHub Actions artifacts (14-day retention).
11. Reports `READY_FOR_TAG` only if **both** Python legs succeeded.

## What it deliberately does not do

- Choose the next version
- Edit `pyproject.toml`
- Edit `CHANGELOG.md`
- Infer a version from Git history or commit messages
- Create a Git tag
- Create a GitHub Release
- Publish to any package index
- Auto-merge
- Change branch protection
- Grant `contents: write`, `packages: write`, or `id-token: write`

Ordinary PR/push CI remains `.github/workflows/ci.yml` and is separate.

## Permissions

```yaml
permissions:
  contents: read
```

CI artifacts are workflow evidence, not a public release.

## Outputs

Local or CI output directory:

```text
dist-release-candidate/
├── cnc_production_shop-<version>-py3-none-any.whl
├── SHA256SUMS
├── release_manifest_<version>.json
├── release_evidence_<version>.md
├── release_notes_<version>.md
└── artifact_verification_<version>.json
```

These paths are gitignored. They are not the canonical distribution.

## Compact summary

A successful run prints:

```text
RELEASE CANDIDATE: 0.1.2
SOURCE SHA: ...
VERSION AUTHORITY: PASS
TESTS: PASS
WHEEL BUILD: PASS
FRESH INSTALL: PASS
PACKAGE PARITY: PASS
MANIFEST: PASS
SHA-256: ...
TAG ELIGIBILITY: PASS

RESULT: READY_FOR_TAG
```

A blocked run prints:

```text
RESULT: BLOCKED
BLOCKERS:
- ...
```

There is no ambiguous “green” result.

Verification completion and tag eligibility are distinct. A candidate
whose wheel, fresh install, parity, and manifest checks passed, and
whose only blocker is that `v<VERSION>` already exists, is:

```text
VERIFICATION: PASS
TAG ELIGIBILITY: FAIL
RESULT: BLOCKED
BLOCKERS:
- canonical tag v<VERSION> already exists
```

That is not a verification-leg failure. The matrix job stays green when
verification completed. The aggregator still reports `BLOCKED` and
exits nonzero so the run cannot be read as `READY_FOR_TAG`.

### `READY_FOR_TAG`

Verification evidence is complete for the requested version at the
inspected commit. A human may now decide whether to authorize the
canonical tag `v<VERSION>`.

It is **not** authorization to tag, merge, or publish.

### `BLOCKED`

Do not tag or publish on the basis of this run. Read the blocker list.

A candidate is `BLOCKED` when any of these fail: version authority,
changelog/notes evidence, tests, wheel build/inspection, fresh install,
package parity, manifest validation, tag eligibility, or either Python
matrix leg.

Tag eligibility fails closed if `v<VERSION>` already exists.
The historical witness tag `msme-001-foundation-original` is ignored.

## Local reproduction

Run tests first (this utility does not invoke pytest, to avoid nested
test runs):

```bash
python -m pytest
python -m ruff check .
python -m mypy musical_spatial_mapping --strict
python -m mypy business --ignore-missing-imports

python scripts/release/build_release_candidate.py \
  --version 0.1.2 \
  --output-dir dist-release-candidate \
  --test-summary "local pytest passed"
```

The requested version must already equal `[project].version`.
Mismatch fails closed. The tool will not rewrite the project to fit.

Against current `main` (`0.1.1` / tag `v0.1.1`) a local run is expected
to report `BLOCKED` because the canonical tag already exists. That is
the eligibility gate working. Use a synthetic tree, or a future
declared version that is not yet tagged, to exercise `READY_FOR_TAG`.

## Manual approval remains in control

Sequence after a `READY_FOR_TAG` result:

1. Human reviews the evidence artifacts and release notes.
2. Human authorizes the canonical tag, if at all.
3. Human performs any later publication only under a separate order.

Follow-on:

```text
CNC-RELEASE-PUBLISHING-1
```

Do not begin publishing automation merely because verification is
automated.
