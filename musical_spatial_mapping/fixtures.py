"""Built-in instrument-profile fixtures for tests and examples.

Dev Order: MSME-001

These load the bundled JSON resource files (the single source of truth) so tests
and the example script share exactly the profiles shipped in the package. Loading
goes through ``instrument_profile_from_dict``, so every fixture is validated.
"""

import json
from importlib.resources import files

from .models import InstrumentProfile
from .serialization import instrument_profile_from_dict

_EXAMPLES = files(__package__).joinpath("resources", "instruments", "examples")


def _load(filename: str) -> InstrumentProfile:
    text = _EXAMPLES.joinpath(filename).read_text(encoding="utf-8")
    return instrument_profile_from_dict(json.loads(text))


def guitar_standard_6() -> InstrumentProfile:
    """Six-string guitar, standard tuning, 22 frets."""
    return _load("guitar-standard-6.json")


def bass_fretless_4() -> InstrumentProfile:
    """Four-string fretless bass."""
    return _load("bass-fretless-4.json")


def mandolin_standard() -> InstrumentProfile:
    """Eight-string mandolin in four courses."""
    return _load("mandolin-standard.json")


def all_example_profiles() -> tuple[InstrumentProfile, ...]:
    """Every bundled example profile, in a stable order."""
    return (guitar_standard_6(), bass_fretless_4(), mandolin_standard())
