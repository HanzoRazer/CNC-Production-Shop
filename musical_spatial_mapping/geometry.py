"""Position mathematics for the Musical Spatial Mapping Engine.

Dev Order: MSME-001

This module owns the equal-temperament geometry and nothing else. For a scale
length ``L`` and a semitone offset ``n`` from the open string, the distance from
the nut to that pitch's location is::

    distance = L * (1 - 2 ** (-n / 12))

The same formula gives both the physical location of an equal-tempered fret and
the target location of a pitch on an idealized fretless string. Fractional ``n``
is supported (fretless / microtonal targets). Negative offsets are rejected: a
pitch below the open string has no location on that string.

12-TET is the first and only geometry model in MSME-001. A later sprint may add
alternate temperaments; this module documents the assumption in one place.
"""

# Positions this many semitones apart or closer are treated as coincident when
# comparing floating-point results. Centralized so tests and callers agree.
POSITION_EPSILON = 1e-9


def _require_nonnegative_offset(semitone_offset: float) -> None:
    if not _is_finite(semitone_offset):
        raise ValueError(f"semitone_offset must be finite, got {semitone_offset!r}")
    if semitone_offset < 0:
        raise ValueError(
            f"semitone_offset must be >= 0 (a pitch below the open string has no "
            f"location on this string), got {semitone_offset}"
        )


def normalized_position_for_semitones(semitone_offset: float) -> float:
    """Fraction of the scale length from the nut, in ``[0, 1)``.

    Independent of physical scale length, so a renderer can place a marker without
    knowing the instrument's dimensions. ``0`` semitones -> ``0.0``; ``12`` -> ``0.5``;
    ``24`` -> ``0.75``.
    """
    _require_nonnegative_offset(semitone_offset)
    return float(1.0 - 2.0 ** (-semitone_offset / 12.0))


def distance_from_nut_mm(scale_length_mm: float, semitone_offset: float) -> float:
    """Physical distance from the nut, in millimetres."""
    _require_scale_length(scale_length_mm)
    _require_nonnegative_offset(semitone_offset)
    return scale_length_mm * normalized_position_for_semitones(semitone_offset)


def fret_distance_from_nut_mm(scale_length_mm: float, fret_number: int) -> float:
    """Physical distance from the nut to a whole-numbered fret, in millimetres."""
    if not isinstance(fret_number, int) or isinstance(fret_number, bool):
        raise ValueError(f"fret_number must be an int, got {fret_number!r}")
    if fret_number < 0:
        raise ValueError(f"fret_number must be >= 0, got {fret_number}")
    return distance_from_nut_mm(scale_length_mm, float(fret_number))


def _require_scale_length(scale_length_mm: float) -> None:
    if not _is_finite(scale_length_mm):
        raise ValueError(f"scale_length_mm must be finite, got {scale_length_mm!r}")
    if scale_length_mm <= 0:
        raise ValueError(f"scale_length_mm must be > 0, got {scale_length_mm}")


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
