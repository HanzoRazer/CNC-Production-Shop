# Release Candidate Automation

Status: Accepted
Order: CNC-RELEASE-AUTOMATION-1
Date: 2026-09-01

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

```text
verification
!= eligibility
!= authorization
!= publication
```

Release candidate verification may be automated. Release identity, tag
authorization, and external publication remain governed manual
decisions. Even `READY_FOR_TAG` is not authorization to create a tag or
publish.

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
3. Rejects malformed identity inputs (`expected_commit`, `release_state`)
   as invocation/configuration errors before building.
4. Runs ruff, mypy, pytest, and repository validators.
5. Builds the wheel.
6. Inspects the wheel (filename, METADATA, duplicate members, packages,
   MSME resources, SHA-256).
7. Installs the wheel into a fresh virtualenv outside the checkout.
8. Verifies site-packages imports, package version parity,
   `MSME_API_VERSION`, packaged resources, MSME CLI, and `cam-assist`.
9. Generates a `release_candidate` manifest and validates it.
10. Writes a human-readable evidence report.
11. Uploads those files as GitHub Actions artifacts (14-day retention),
    including when the candidate is `BLOCKED`.
12. Aggregates semantic candidate results from both Python legs and
    reports `READY_FOR_TAG`, `BLOCKED`, or `FAILED`.

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
├── release_evidence_<version>.json
├── release_evidence_<version>.md
├── release_notes_<version>.md
└── artifact_verification_<version>.json
```

These paths are gitignored. They are not the canonical distribution.

## Candidate dispositions

Every evaluated candidate has exactly one of:

```text
READY_FOR_TAG
BLOCKED
FAILED
```

Blockers and failures are different channels. A policy blocker must not
be recorded as a verification failure.

```text
verification_status:  PASS | FAIL
eligibility_status:   PASS | BLOCKED | NOT_EVALUATED
disposition:          READY_FOR_TAG | BLOCKED | FAILED
result:               alias of disposition
blockers:             eligibility / release-readiness conditions
failures:             verification / evidence defects
```

`FAILED` takes precedence when both channels are populated.
Eligibility is evaluated independently when that is safe. If a failure
makes eligibility unknowable, `eligibility_status` is `NOT_EVALUATED`
rather than a fabricated blocker.

### `READY_FOR_TAG`

Verification passed and eligibility passed. Evidence is complete for the
requested version at the inspected commit. A human may now decide
whether to authorize the canonical tag `v<VERSION>`.

It is **not** authorization to tag, merge, or publish.

### `BLOCKED`

Verification passed and one or more policy/eligibility blockers exist.

`BLOCKED` is a valid verification outcome, not a verification
malfunction.

Do not tag or publish on the basis of this run. Read the blocker list.

Typical blockers:

- canonical tag `v<VERSION>` already exists
- dirty release tree
- CHANGELOG not release-ready
- release notes not release-ready
- other genuine release-readiness/policy conditions

Tag eligibility fails closed if `v<VERSION>` already exists.
The historical witness tag `msme-001-foundation-original` is ignored.

Against current `main` (`0.1.1` / tag `v0.1.1`) a correctly classified
run reports:

```text
verification_status: PASS
eligibility_status: BLOCKED
disposition: BLOCKED
blockers:
- canonical tag v0.1.1 already exists
failures: []
```

Evidence (wheel, SHA256SUMS, manifest, release evidence, notes preview,
artifact-verification JSON) is preserved for `BLOCKED`.

### `FAILED`

Verification or evidence generation failed. Examples: test evidence
missing, wheel build failure, duplicate wheel member, fresh-install
failure, package-version drift, manifest failure, resource failure,
CLI failure, artifact verification failure.

## Invocation and configuration errors

These are not candidate dispositions. The command exits `3` and does
not build a wheel:

- malformed version
- malformed `expected_commit`
- unauthorized `release_state`
- requested version does not match the authoritative project version
- `expected_commit` is valid syntax but does not equal HEAD

A candidate that never validly existed does not receive an evidence
bundle.

## CLI exit codes

```text
0  READY_FOR_TAG or BLOCKED   (evaluation succeeded)
2  FAILED                     (verification/evidence failure)
3  invocation/configuration error
```

The GitHub `summarize` job inspects `disposition`. It is red for both
`BLOCKED` and `FAILED` so there is no ambiguous green, but it reports
those outcomes accurately. It must not describe a blocked candidate as
“verification legs failed.”

## Compact summary

A ready run prints:

```text
RELEASE CANDIDATE: 0.1.2
...
VERIFICATION: PASS
ELIGIBILITY: PASS
DISPOSITION: READY_FOR_TAG

RESULT: READY_FOR_TAG
```

A blocked run prints:

```text
VERIFICATION: PASS
ELIGIBILITY: BLOCKED
DISPOSITION: BLOCKED

RESULT: BLOCKED
BLOCKERS:
- canonical tag v0.1.1 already exists
FAILURES:
- none
```

A failed run prints:

```text
VERIFICATION: FAIL
DISPOSITION: FAILED

RESULT: FAILED
FAILURES:
- ...
```

There is no ambiguous “green” result.

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
Mismatch is an invocation error. The tool will not rewrite the project
to fit.

Against current `main` (`0.1.1` / tag `v0.1.1`) a local run is expected
to report `BLOCKED` because the canonical tag already exists. That is
the eligibility gate working, not a verification malfunction. Use a
synthetic tree, or a future declared version that is not yet tagged, to
exercise `READY_FOR_TAG`.

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
