# CNC Production Shop

Integrated platform for CNC lutherie workflows — from design through manufacturing.

## Overview

CNC Production Shop is a comprehensive toolkit for instrument builders working with CNC technology. The platform bridges the gap between creative design intent and precision manufacturing execution.

### Core Capabilities

- **CAM Assist** — Human-guided manufacturing intelligence for reviewable, portable strategy packages
- **Parametric Guitar Designer** — AI-assisted body shape ideation with dimensional grounding
- **Fret Slot Strategy** — Precision fretboard layout and toolpath generation
- **Wood Database** — Species characterization for material selection
- **Acoustic Studio** — Soundhole and bracing design tools

## Philosophy

```
Manufacturing assistance ≠ Manufacturing authority
```

The system augments expert judgment — it does not replace it. All manufacturing decisions require human review and approval.

## Project Status

```
Active Development
```

This repository consolidates lutherie manufacturing tools under a unified platform architecture.

## Structure

```
CNC-Production-Shop/
├── cam_assist/          # CAM strategy packaging and review
├── parametric/          # Body shape design tools
├── fretboard/           # Fret layout and calculation
├── materials/           # Wood database and characterization
├── acoustic/            # Sound design tools
├── schemas/             # Shared JSON schemas
├── scripts/             # CLI utilities
└── tests/               # Test suite
```

## Requirements

- Python 3.11+
- See `pyproject.toml` for dependencies

## Installation

```bash
pip install -e .
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy cam_assist
```

## License

MIT License — Copyright © 2026 Texas Guitar Exchange LLC
