# cnc-production-shop 0.1.1

## Changed
- Packaged `__version__` attributes now report the containing

## Fixed
- `pip wheel` no longer fails on duplicate
- MSME CLI serialization uses the library serializer so CLI and library

## Packaging
- Packaging tests build a real wheel and fail in CI when the artifact cannot
- Fresh-venv install, site-packages import, and metadata parity are gated.

## Governance
- Established distribution version authority, release numbering, tagging,
- First governed release identity is `REL-CNC-0.1.1`. Canonical tag is
