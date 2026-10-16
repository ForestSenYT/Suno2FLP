"""Read-only exact event/clock comparisons; no import mapping or host execution."""

import json
from bisect import bisect_right
from collections import defaultdict, deque
from fractions import Fraction
from pathlib import Path

from suno2flp.core.encoding_assessment import SignedRatio
from suno2flp.core.midi_comparison import (
    MidiClockDifference,
    MidiEventAddress,
    MidiEventComparison,
    MidiEventMatch,
)
from suno2flp.core.models import Diagnostic, ProcessedMidi
from suno2flp.core.offline_files import capture_input, load_unique_json, verify_inputs
from suno2flp.core.performance import RationalTime
from suno2flp.importer import MidiFileImporter

EventKey = tuple[Fraction, str]


def _event_keys(midi: ProcessedMidi) -> list[list[EventKey]]:
    # Exclude only the serialized delta: the absolute position has exact PPQ units.
    # Retain meta events, note-off forms, channel, release velocity and duplicates.
    return [
        [
            (
                Fraction(event.tick, midi.ticks_per_beat),
                json.dumps(
                    {key: value for key, value in event.message.items() if key != "time"},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            for event in track.events
        ]
        for track in midi.tracks
    ]


def _match_events(
    expected: list[list[EventKey]], candidate: list[list[EventKey]]
) -> tuple[list[MidiEventMatch], list[MidiEventAddress], list[MidiEventAddress]]:
    available: dict[EventKey, deque[MidiEventAddress]] = defaultdict(deque)
    for track, events in enumerate(candidate):
        for index, key in enumerate(events):
            available[key].append(MidiEventAddress(track_position=track, event_index=index))
    matches, missing = [], []
    for track, events in enumerate(expected):
        for index, key in enumerate(events):
            address = MidiEventAddress(track_position=track, event_index=index)
            if available[key]:
                matches.append(MidiEventMatch(expected=address, candidate=available[key].popleft()))
            else:
                missing.append(address)
    extra = sorted(
        (address for remaining in available.values() for address in remaining),
        key=lambda address: (address.track_position, address.event_index),
    )
    return matches, missing, extra


class _Clock:
    def __init__(self, midi: ProcessedMidi) -> None:
        values: dict[Fraction, set[int]] = defaultdict(set)
        for tempo in midi.tempo_map:
            values[Fraction(tempo.tick, midi.ticks_per_beat)].add(tempo.microseconds_per_beat)
        if any(len(group) != 1 for group in values.values()):
            raise ValueError("Conflicting tempo values at the same beat")
        points = {beat: next(iter(group)) for beat, group in values.items()}
        points.setdefault(Fraction(0), 500000)
        self.beats = sorted(points)
        self.periods = [points[beat] for beat in self.beats]
        self.elapsed = [Fraction(0)]
        for i in range(1, len(self.beats)):
            self.elapsed.append(
                self.elapsed[-1] + (self.beats[i] - self.beats[i - 1]) * self.periods[i - 1]
            )

    def at(self, beat: Fraction) -> Fraction:
        index = bisect_right(self.beats, beat) - 1
        return self.elapsed[index] + (beat - self.beats[index]) * self.periods[index]


def _clocks(
    expected: ProcessedMidi, candidate: ProcessedMidi, end: Fraction
) -> tuple[list[MidiClockDifference], RationalTime | None, list[Diagnostic]]:
    if any(d.code == "invalid_tempo" for midi in (expected, candidate) for d in midi.diagnostics):
        # Import retains the raw event but cannot add its zero period to the map.
        # Falling back to MIDI's default would invent a valid source clock.
        return [], None, []
    try:
        left, right = _Clock(expected), _Clock(candidate)
    except ValueError:
        return (
            [],
            None,
            [
                Diagnostic(
                    code="midi_comparison_tempo_conflict",
                    severity="error",
                    message="Same-beat tempo values conflict; no playback order is assumed",
                )
            ],
        )
    differences = []
    maximum = Fraction(0)
    # The difference is linear between the union of tempo boundaries. Include the
    # common horizon so cancellation cannot conceal an earlier maximum.
    for beat in sorted({Fraction(0), end, *left.beats, *right.beats}):
        if beat > end:
            continue
        a, b = left.at(beat), right.at(beat)
        delta = b - a
        maximum = max(maximum, abs(delta))
        if delta:
            differences.append(
                MidiClockDifference(
                    beat=RationalTime.exact(beat),
                    expected_microseconds=RationalTime.exact(a),
                    candidate_microseconds=RationalTime.exact(b),
                    candidate_minus_expected_microseconds=SignedRatio.exact(delta),
                )
            )
    return differences, RationalTime.exact(maximum), []


def compare_midi_events(expected_file: Path, candidate_file: Path) -> MidiEventComparison:
    identities = [capture_input(path)[0] for path in (expected_file, candidate_file)]
    imported = [MidiFileImporter().import_file(identity.path) for identity in identities]
    for identity, midi in zip(identities, imported, strict=True):
        if identity.sha256 != midi.source_sha256:
            raise ValueError("Input changed during MIDI import")
    expected, candidate = imported
    expected_keys, candidate_keys = _event_keys(expected), _event_keys(candidate)
    matches, missing, extra = _match_events(expected_keys, candidate_keys)
    end = max(
        Fraction(track.end_tick, midi.ticks_per_beat) for midi in imported for track in midi.tracks
    )
    differences, maximum, diagnostics = _clocks(expected, candidate, end)
    diagnostics.extend(d.model_copy(deep=True) for midi in imported for d in midi.diagnostics)
    events_equal = not missing and not extra
    ordered = expected_keys == candidate_keys
    clock_equal = None if maximum is None else maximum.numerator == 0
    report = MidiEventComparison(
        input_files=identities,
        referenced_paths=[identity.path for identity in identities],
        expected=expected,
        candidate=candidate,
        matches=matches,
        missing=missing,
        extra=extra,
        events_equal=events_equal,
        ordered_tracks_equal=ordered,
        compared_through_beat=RationalTime.exact(end),
        clock_differences=differences,
        maximum_clock_error_microseconds=maximum,
        clock_equal=clock_equal,
        equivalent=(
            events_equal
            and ordered
            and clock_equal is True
            and not any(d.severity == "error" for d in diagnostics)
        ),
        diagnostics=diagnostics,
    )
    verify_inputs(identities)
    return report


def verify_midi_comparison(path: Path) -> MidiEventComparison:
    identity, raw = capture_input(path)
    saved = MidiEventComparison.model_validate(load_unique_json(raw))
    if len(saved.input_files) != 2:
        raise ValueError("MIDI comparison replay needs exactly two input files")
    rebuilt = compare_midi_events(saved.input_files[0].path, saved.input_files[1].path)
    if saved != rebuilt:
        raise ValueError("MIDI comparison replay mismatch")
    verify_inputs([identity, *rebuilt.input_files])
    return rebuilt
