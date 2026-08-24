# cnc-production-shop 0.1.1

Date: 2026-08-24

Release ID: REL-CNC-0.1.1
State: release_candidate
Tag: v0.1.1 (proposed)
Distribution: cnc-production-shop

This is the first governed distribution release. `0.1.0` was a version
declaration only and was never tagged.

## Highlights

- The installable wheel builds and installs.
- Package `__version__` values follow the distribution version.
- Release numbering, evidence, and tagging are now governed.
- MSME contract maturity stays `MSME_API_VERSION` `0.2.0`.

## Changed

- Packaged `__version__` attributes now report the containing
  `cnc-production-shop` distribution version through
  `cnc_version.distribution_version()`. MSME public-contract maturity remains
  `MSME_API_VERSION` (`0.2.0`).

## Fixed

- `pip wheel` no longer fails on duplicate
  `musical_spatial_mapping` resource members.
- MSME CLI serialization uses the library serializer so CLI and library
  output bytes match.

## Packaging

- Packaging tests build a real wheel and fail in CI when the artifact cannot
  be produced, instead of skipping.
- Fresh-venv install, site-packages import, and metadata parity are gated.

## Governance

- Established distribution version authority, release numbering, tagging,
  changelog, and evidence rules.
- First governed release identity is `REL-CNC-0.1.1`. Canonical tag is
  `v0.1.1`. `0.1.0` remains a historical version declaration, not a tagged
  release.

## Subsystem Versions

- `MSME_API_VERSION`: `0.2.0` (unchanged)

## Known Limitations

- Publication remains internal-only. This execution does not create a GitHub
  Release and does not upload to PyPI or any other index.
- The historical witness tag `msme-001-foundation-original` is not a
  distribution release.

## Verification

Recorded during CNC-RELEASE-EXECUTION-1. Final SHA, wheel hash, and CI run
IDs are in `docs/releases/RELEASE_EVIDENCE_0.1.1.md` and
`fixtures/releases/release_manifest_0.1.1.json`.

## Artifacts

- Wheel: `cnc_production_shop-0.1.1-py3-none-any.whl`
- Hash file: `dist-release/SHA256SUMS`
- Wheel bytes are not stored in git; rebuild from the tagged commit.
