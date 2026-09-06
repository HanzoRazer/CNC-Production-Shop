# Changelog

## Unreleased

## [0.1.1] - 2026-08-24

### Changed
- Packaged `__version__` attributes now report the containing
  `cnc-production-shop` distribution version through
  `cnc_version.distribution_version()`. MSME public-contract maturity remains
  `MSME_API_VERSION` (`0.2.0`).

### Fixed
- `pip wheel` no longer fails on duplicate
  `musical_spatial_mapping` resource members.
- MSME CLI serialization uses the library serializer so CLI and library
  output bytes match.

### Packaging
- Packaging tests build a real wheel and fail in CI when the artifact cannot
  be produced, instead of skipping.
- Fresh-venv install, site-packages import, and metadata parity are gated.

### Governance
- Established distribution version authority, release numbering, tagging,
  changelog, and evidence rules.
- First governed release identity is `REL-CNC-0.1.1`. Canonical tag is
  `v0.1.1`. `0.1.0` remains a historical version declaration, not a tagged
  release.
