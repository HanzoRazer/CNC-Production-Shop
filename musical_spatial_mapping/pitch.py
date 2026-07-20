"""Pitch utilities independent of instrument geometry.

Dev Order: MSME-001

These helpers know about MIDI note numbers and 12-TET pitch spelling. They know
nothing about strings, frets, or scale length. Spatial mapping must not depend on
enharmonic spelling; ``format_pitch_name`` is for annotation only.
"""

_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

MIDI_MIN = 0
MIDI_MAX = 127


def _require_midi(midi_note: int) -> None:
    if not isinstance(midi_note, int) or isinstance(midi_note, bool):
        raise ValueError(f"MIDI note must be an int, got {midi_note!r}")
    if not MIDI_MIN <= midi_note <= MIDI_MAX:
        raise ValueError(f"MIDI note {midi_note} out of range {MIDI_MIN}-{MIDI_MAX}")


def midi_note_to_pitch_class(midi_note: int) -> int:
    """Return the pitch class 0-11 (C=0)."""
    _require_midi(midi_note)
    return midi_note % 12


def midi_note_to_octave(midi_note: int) -> int:
    """Return the scientific-pitch octave (MIDI 60 = C4)."""
    _require_midi(midi_note)
    return midi_note // 12 - 1


def format_pitch_name(midi_note: int, *, prefer_flats: bool = False) -> str:
    """Return a spelled pitch name such as ``"E4"`` or ``"C#4"`` / ``"Db4"``.

    Spelling is presentation only and never affects mapping.
    """
    _require_midi(midi_note)
    names = _FLAT_NAMES if prefer_flats else _SHARP_NAMES
    return f"{names[midi_note % 12]}{midi_note_to_octave(midi_note)}"


def pitch_distance_semitones(
    source_midi: int,
    target_midi: int,
    cents_offset: float = 0.0,
) -> float:
    """Signed distance in semitones from ``source_midi`` to ``target_midi``.

    A nonzero ``cents_offset`` (hundredths of a semitone) is folded in, yielding a
    fractional result used only where microtonal positions are permitted.
    """
    _require_midi(source_midi)
    _require_midi(target_midi)
    if not _is_finite(cents_offset):
        raise ValueError(f"cents_offset must be finite, got {cents_offset!r}")
    return (target_midi - source_midi) + cents_offset / 100.0


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
