"""Compile every source event to exact time; no binary encoding or process launch."""

from bisect import bisect_right
from collections import Counter
from fractions import Fraction
from pathlib import Path

from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.models import Arrangement, Diagnostic
from suno2flp.core.offline_files import capture_input, load_unique_json, verify_inputs
from suno2flp.core.performance import (
    PerformanceEvent,
    PerformanceEventAddress,
    PerformanceNote,
    PerformancePlan,
    PerformancePosition,
    PerformanceTempo,
    PerformanceTrack,
    RationalTime,
)
from suno2flp.flp_builder.writer_intent import METADATA_EVENTS
from suno2flp.validator.arrangement import verify_arrangement_file


class _Clock:
    def __init__(self, arrangement: Arrangement, target_ppq: int) -> None:
        self.target_ppq = target_ppq
        self.beats = [Fraction(t.tick, arrangement.ticks_per_beat) for t in arrangement.tempo_map]
        self.tempos = [t.microseconds_per_beat for t in arrangement.tempo_map]
        self.elapsed = [Fraction(0)]
        if (
            not self.beats
            or self.beats[0] != 0
            or any(right <= left for left, right in zip(self.beats, self.beats[1:], strict=False))
        ):
            raise ValueError("Performance replay requires an ordered effective tempo map from zero")
        for index in range(1, len(self.beats)):
            self.elapsed.append(
                self.elapsed[-1]
                + (self.beats[index] - self.beats[index - 1]) * self.tempos[index - 1]
            )
        self.inexact = 0
        self.out_of_range = 0

    def at(self, tick: int, ppq: int) -> PerformancePosition:
        beat = Fraction(tick, ppq)
        index = bisect_right(self.beats, beat) - 1
        target = beat * self.target_ppq
        self.inexact += target.denominator != 1
        self.out_of_range += target > 2**31 - 1
        return PerformancePosition(
            target_tick=RationalTime.exact(target),
            elapsed_microseconds=RationalTime.exact(
                self.elapsed[index] + (beat - self.beats[index]) * self.tempos[index]
            ),
        )


def plan_performance_file(
    arrangement_file: Path, *, target_ppq: int | None = None
) -> PerformancePlan:
    """Reimport current originals; successful analysis never permits writing."""
    identity, raw = capture_input(arrangement_file)
    arrangement = Arrangement.model_validate(load_unique_json(raw))
    target = arrangement.ticks_per_beat if target_ppq is None else target_ppq
    if type(target) is not int or not 1 <= target <= 65535:
        raise ValueError("Target PPQ must be an integer in 1..65535 (not a host support claim)")
    quality = verify_arrangement_file(arrangement_file)
    if not quality.valid or not quality.input_files or quality.input_files[0] != identity:
        raise ValueError(
            "Performance source replay failed: "
            + "; ".join(item.message for item in quality.diagnostics)
        )
    if arrangement.build_options is None or arrangement.build_options.ppq_rounding != "error":
        raise ValueError("Performance preservation forbids prior PPQ rounding policy")
    if any(d.code == "timing_conflict_overridden" for d in arrangement.diagnostics):
        raise ValueError("Performance preservation forbids overridden timing maps")
    if any(
        source.note_view == "cleaned" and source.midi.cleanup and source.midi.cleanup.changes
        for source in arrangement.sources
    ):
        raise ValueError("Performance preservation forbids selected cleanup changes")

    clock = _Clock(arrangement, target)
    tracks = []
    untranslated = []
    counts: Counter[str] = Counter()
    source_diagnostics: Counter[str] = Counter()
    for source in arrangement.sources:
        source_diagnostics.update(d.code for d in source.midi.diagnostics)
        for position, track in enumerate(source.midi.tracks):
            if track.index is None:
                raise ValueError("Performance replay requires original track indices")
            events = []
            for event in track.events:
                events.append(
                    PerformanceEvent(
                        source_event_index=event.event_index,
                        position=clock.at(event.tick, source.midi.ticks_per_beat),
                    )
                )
                kind = str(event.message.get("type"))
                counts[kind] += 1
                if kind not in METADATA_EVENTS | {"note_on", "note_off"}:
                    channel = event.message.get("channel")
                    untranslated.append(
                        PerformanceEventAddress(
                            source_input=source.input_index,
                            source_track_position=position,
                            source_event_index=event.event_index,
                            event_type=kind,
                            source_channel=channel if isinstance(channel, int) else None,
                        )
                    )
            tracks.append(
                PerformanceTrack(
                    source_input=source.input_index,
                    source_track_position=position,
                    source_track_index=track.index,
                    events=events,
                    end=clock.at(track.end_tick, source.midi.ticks_per_beat),
                )
            )

    notes = []
    zero_durations = 0
    for track_index, arranged_track in enumerate(arrangement.tracks):
        for note_index, note in enumerate(arranged_track.notes):
            zero_durations += note.duration_ticks == 0
            notes.append(
                PerformanceNote(
                    arrangement_track_position=track_index,
                    note_index=note_index,
                    start=clock.at(note.start_tick, arrangement.ticks_per_beat),
                    end=clock.at(note.start_tick + note.duration_ticks, arrangement.ticks_per_beat),
                )
            )
    tempos = []
    for tempo in arrangement.tempo_map:
        value = Fraction(60_000_000_000, tempo.microseconds_per_beat)
        tempos.append(
            PerformanceTempo(
                source=tempo.model_copy(deep=True),
                position=clock.at(tempo.tick, arrangement.ticks_per_beat),
                milli_bpm=RationalTime.exact(value),
                exact_milli_bpm=value.numerator if value.denominator == 1 else None,
            )
        )
    # Meter positions also have to fit: they may occur on otherwise empty tracks.
    for meter in arrangement.meter_map:
        clock.at(meter.tick, arrangement.ticks_per_beat)
    diagnostics = [
        Diagnostic(
            code="performance_template_evidence_required",
            severity="error",
            message="No template/prototypes/routing or host acceptance is authorized by this plan",
        )
    ]

    def block(condition: bool, code: str, message: str) -> None:
        if condition:
            diagnostics.append(Diagnostic(code=code, severity="error", message=message))

    scalar_inexact = sum(t.exact_milli_bpm is None for t in tempos)
    block(
        bool(clock.inexact),
        "performance_ppq_inexact",
        "Some target positions are fractional; original rational positions retained, never rounded",
    )
    block(
        bool(clock.out_of_range),
        "performance_tick_range",
        "Some target positions exceed the existing writer signed 32-bit range",
    )
    block(
        bool(scalar_inexact),
        "performance_tempo_scalar_inexact",
        f"{scalar_inexact} effective tempos cannot fit the existing integer milli-BPM scalar",
    )
    block(
        any(t.exact_milli_bpm is not None and not 0 < t.exact_milli_bpm <= 999000 for t in tempos),
        "performance_tempo_scalar_range",
        "Exact scalar outside the current writer range",
    )
    block(
        len(tempos) > 1,
        "performance_tempo_automation_unverified",
        "FL26 tempo automation addressing, value encoding and step semantics remain unverified",
    )
    block(
        len(arrangement.meter_map) != 1
        or any(
            (
                meter.numerator,
                meter.denominator,
                meter.clocks_per_click,
                meter.notated_32nd_notes_per_beat,
            )
            != (4, 4, 24, 8)
            for meter in arrangement.meter_map
        ),
        "performance_meter_encoding_unverified",
        "The existing writer cannot encode this meter map; original events remain unchanged",
    )
    block(
        bool(untranslated),
        "performance_event_routing_unverified",
        f"{len(untranslated)} source events require proven FL encoding/routing; none omitted",
    )
    block(
        bool(zero_durations),
        "performance_zero_duration",
        f"{zero_durations} zero-duration notes retained; writer requires positive length",
    )
    block(
        bool(source_diagnostics),
        "performance_source_diagnostics",
        f"Source diagnostics retained for review: {dict(source_diagnostics)}",
    )
    verify_inputs(quality.input_files)
    return PerformancePlan(
        arrangement_file=identity,
        arrangement_fingerprint=snapshot_sha256(arrangement),
        arrangement=arrangement,
        input_files=quality.input_files,
        referenced_paths=quality.referenced_paths,
        target_ppq=target,
        target_grid_exact=not clock.inexact,
        tempo_scalar_exact=not scalar_inexact,
        tracks=tracks,
        notes=notes,
        tempos=tempos,
        untranslated_events=untranslated,
        event_type_counts=dict(counts),
        diagnostics=diagnostics,
    )


def verify_performance_file(path: Path) -> PerformancePlan:
    """Reject altered/obsolete reports by recomputing every field from current originals."""
    identity, raw = capture_input(path)
    saved = PerformancePlan.model_validate(load_unique_json(raw))
    rebuilt = plan_performance_file(saved.arrangement_file.path, target_ppq=saved.target_ppq)
    if rebuilt != saved:
        raise ValueError("Performance plan replay mismatch; report fields are not authoritative")
    verify_inputs([identity, *rebuilt.input_files])
    return rebuilt
