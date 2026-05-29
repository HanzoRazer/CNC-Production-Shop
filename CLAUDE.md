# CNC Production Shop — Claude Code Instructions

## Project Overview

CNC Production Shop is an integrated platform for CNC lutherie (guitar/instrument building) workflows. It helps instrument builders transform design intent into reviewable, manufacturable strategy packages.

## Key Principles

1. **Human authority preserved** — The system assists but never authorizes manufacturing autonomously
2. **Review-first workflow** — All CAM strategies require human review before execution
3. **Portable packages** — Manufacturing intent packaged for reproducibility and handoff

## Architecture

```
cam_assist/       — CAM strategy packaging, validation, review tooling
parametric/       — Body shape design (AI ideation → dimensional grounding)
fretboard/        — Fret slot calculation and layout
materials/        — Wood species database and characterization
acoustic/         — Soundhole/bracing design tools
schemas/          — JSON schemas for all data structures
```

## Development Commands

```bash
# Run tests
pytest

# Run specific test file
pytest tests/test_cam_assist.py

# Type check
mypy cam_assist

# Lint
ruff check .

# Format
ruff format .
```

## Code Style

- Python 3.11+ with type hints
- Pydantic for data validation
- Click for CLI tools
- JSON schemas for external contracts
- Tests alongside implementation

## Terminology

- **Strategy Package** — Bundled manufacturing intent (toolpaths + metadata + review records)
- **Review Packet** — Human-readable summary for operator review
- **Decision Record** — Captured approval/rejection with rationale
- **Federation** — Cross-package references and provenance tracking

## Related Projects

- `ltb-parametric-guitar` — Parametric body designer (in c:\tmp)
- `fret_slot_strategy_package` — Fretboard toolpath generation (in c:\tmp)
- `CAM-Assist-Blueprint` — Architecture reference (in Downloads)
