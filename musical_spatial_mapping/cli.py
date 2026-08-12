"""Diagnostic command line for the Musical Spatial Mapping Engine.

Dev Order: MSME-002 Phase H

    python -m musical_spatial_mapping.cli --profile PROFILE.json --event '{"midi_note": 64}'

A CONSUMER of the engine, never part of its semantics. Everything here either
turns JSON into an existing domain object or turns a ``MappingResult`` back into
JSON; no scoring, selection or annotation decision is made or duplicated in this
file. If the CLI and a library caller ever disagree about an answer, this module
has a bug.

Inputs are explicit. There is no config file discovery, no environment variable,
and no default profile: an argument names every input, so the same command line
means the same thing on any machine.

**stdout is machine-readable JSON and nothing else.** Prose goes to stderr. A
tool that prints a friendly banner above its JSON cannot be piped anywhere.

**An unplayable pitch exits 0.** It is a valid mapping outcome carrying evidence,
not a process failure, and a caller mapping a melody should not have to treat an
unreachable note as a crashed command.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .enums import OpenStringPolicy
from .errors import SpatialMappingError
from .mapper import MusicalSpatialMapper
from .models import (
    MappingConstraints,
    MappingPreferences,
    MappingResult,
    MusicalEvent,
    SpatialPosition,
)
from .serialization import (
    instrument_profile_from_dict,
    mapping_result_to_json,
    spatial_position_from_dict,
)

EXIT_OK = 0
EXIT_INPUT_ERROR = 1


class CliInputError(Exception):
    """A problem with what the caller supplied, reported without a traceback."""


def _load_json(*, inline: str | None, path: str | None, label: str) -> Any | None:
    """Read one JSON input from either an inline string or a file."""
    if inline is not None and path is not None:
        raise CliInputError(f"{label}: give either the inline form or a file, not both")
    if inline is None and path is None:
        return None
    source = inline if inline is not None else Path(path or "").read_text(encoding="utf-8")
    try:
        return json.loads(source)
    except json.JSONDecodeError as exc:
        raise CliInputError(f"{label}: invalid JSON ({exc.msg} at line {exc.lineno})") from exc


def _require_mapping(data: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise CliInputError(f"{label}: expected a JSON object")
    return data


def _event_from(data: Mapping[str, Any]) -> MusicalEvent:
    """Translate JSON into the existing event contract.

    Only ``midi_note`` is required; the remaining fields carry the model's own
    defaults so a one-note diagnostic invocation stays short.
    """
    if "midi_note" not in data:
        raise CliInputError("event: 'midi_note' is required")
    return MusicalEvent(
        event_id=data.get("event_id", "cli-event"),
        midi_note=data["midi_note"],
        start_tick=data.get("start_tick", 0),
        duration_ticks=data.get("duration_ticks", 480),
        velocity=data.get("velocity", 64),
        cents_offset=data.get("cents_offset", 0.0),
        voice_id=data.get("voice_id"),
    )


def _constraints_from(data: Mapping[str, Any] | None) -> MappingConstraints:
    if data is None:
        return MappingConstraints()
    allowed = data.get("allowed_string_ids")
    return MappingConstraints(
        allowed_string_ids=None if allowed is None else frozenset(allowed),
        excluded_string_ids=frozenset(data.get("excluded_string_ids", ())),
        minimum_position=data.get("minimum_position"),
        maximum_position=data.get("maximum_position"),
        preferred_minimum_position=data.get("preferred_minimum_position"),
        preferred_maximum_position=data.get("preferred_maximum_position"),
        open_string_policy=_policy(data.get("open_string_policy")),
        maximum_string_jump=data.get("maximum_string_jump"),
        capo_fret=data.get("capo_fret", 0),
    )


def _policy(value: Any) -> OpenStringPolicy:
    if value is None:
        return OpenStringPolicy.ALLOW
    try:
        return OpenStringPolicy(value)
    except ValueError as exc:
        allowed = ", ".join(p.value for p in OpenStringPolicy)
        raise CliInputError(
            f"constraints: unknown open_string_policy {value!r} ({allowed})"
        ) from exc


def _preferences_from(data: Mapping[str, Any] | None) -> MappingPreferences:
    if data is None:
        return MappingPreferences()
    defaults = MappingPreferences()
    return MappingPreferences(
        movement_weight=data.get("movement_weight", defaults.movement_weight),
        string_change_weight=data.get("string_change_weight", defaults.string_change_weight),
        position_weight=data.get("position_weight", defaults.position_weight),
        preferred_region_weight=data.get(
            "preferred_region_weight", defaults.preferred_region_weight
        ),
        open_string_weight=data.get("open_string_weight", defaults.open_string_weight),
        lower_position_bias=data.get("lower_position_bias", defaults.lower_position_bias),
    )


def _previous_from(data: Mapping[str, Any] | None) -> SpatialPosition | None:
    """Reuses the Phase G parser rather than re-deriving the position shape."""
    if data is None:
        return None
    return spatial_position_from_dict(data)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m musical_spatial_mapping.cli",
        description="Map one musical event onto playable positions. Emits JSON on stdout.",
    )
    parser.add_argument("--profile", required=True, help="path to an instrument profile JSON file")
    parser.add_argument("--event", help="inline JSON event, e.g. '{\"midi_note\": 64}'")
    parser.add_argument("--event-file", help="path to a JSON event")
    parser.add_argument("--constraints", help="inline JSON mapping constraints")
    parser.add_argument("--constraints-file", help="path to JSON mapping constraints")
    parser.add_argument("--preferences", help="inline JSON mapping preferences")
    parser.add_argument("--preferences-file", help="path to JSON mapping preferences")
    parser.add_argument("--previous-position", help="inline JSON prior SpatialPosition")
    parser.add_argument("--previous-position-file", help="path to a prior SpatialPosition")
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout (default 2; use 0 for one line)",
    )
    return parser


def _run(args: argparse.Namespace) -> MappingResult:
    try:
        profile_data = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliInputError(f"profile: invalid JSON ({exc.msg} at line {exc.lineno})") from exc
    profile = instrument_profile_from_dict(_require_mapping(profile_data, "profile"))

    event_data = _load_json(inline=args.event, path=args.event_file, label="event")
    if event_data is None:
        raise CliInputError("event: supply --event or --event-file")

    mapper = MusicalSpatialMapper(
        profile=profile,
        constraints=_constraints_from(
            _optional_mapping(
                _load_json(
                    inline=args.constraints, path=args.constraints_file, label="constraints"
                ),
                "constraints",
            )
        ),
        preferences=_preferences_from(
            _optional_mapping(
                _load_json(
                    inline=args.preferences, path=args.preferences_file, label="preferences"
                ),
                "preferences",
            )
        ),
    )
    return mapper.map(
        _event_from(_require_mapping(event_data, "event")),
        previous_position=_previous_from(
            _optional_mapping(
                _load_json(
                    inline=args.previous_position,
                    path=args.previous_position_file,
                    label="previous-position",
                ),
                "previous-position",
            )
        ),
    )


def _optional_mapping(data: Any, label: str) -> Mapping[str, Any] | None:
    return None if data is None else _require_mapping(data, label)


def main(argv: Sequence[str] | None = None) -> int:
    """Map one event and print the result as JSON.

    Returns 0 for every mapping OUTCOME, including UNPLAYABLE, and non-zero only
    when the caller's input could not be understood.
    """
    args = _build_parser().parse_args(argv)
    try:
        result = _run(args)
    except (CliInputError, SpatialMappingError) as exc:
        # Concise, no traceback: the caller supplied something wrong and a stack
        # trace would tell them about our frames rather than their input.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except OSError as exc:
        print(f"error: could not read input ({exc.strerror or exc})", file=sys.stderr)
        return EXIT_INPUT_ERROR

    # Serialized through the library rather than by a second json.dumps here, so
    # the CLI and a library caller cannot drift into different byte contracts.
    # ASCII escaping is the serializer's default; indent 0 collapses to one line.
    print(mapping_result_to_json(result, indent=args.indent or None))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
