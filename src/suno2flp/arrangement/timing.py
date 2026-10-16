"""Compare effective source maps in exact beat coordinates before tick conversion."""

from dataclasses import dataclass
from fractions import Fraction
from itertools import groupby
from typing import Literal

from suno2flp.arrangement.ppq import TickConverter
from suno2flp.core.errors import TimingConflictError
from suno2flp.core.models import (
    Arrangement,
    ArrangementOptions,
    Diagnostic,
    MeterEvent,
    ProcessedMidi,
    TempoEvent,
)


@dataclass
class TimingPoint:
    beat: Fraction
    value: tuple[int, ...]
    event: TempoEvent | MeterEvent


def _value(event: TempoEvent | MeterEvent) -> tuple[int, ...]:
    if isinstance(event, TempoEvent):
        return (event.microseconds_per_beat,)
    return (
        event.numerator,
        event.denominator,
        event.clocks_per_click,
        event.notated_32nd_notes_per_beat,
    )


def _timeline(
    source: ProcessedMidi,
    index: int,
    kind: Literal["tempo", "meter"],
    tolerate_conflict: bool,
    diagnostics: list[Diagnostic],
) -> list[TimingPoint]:
    default: TempoEvent | MeterEvent
    events: list[TempoEvent | MeterEvent]
    if kind == "tempo":
        default = TempoEvent(
            tick=0, microseconds_per_beat=500000, is_default=True, source_input=index
        )
        events = [*source.tempo_map]
    else:
        default = MeterEvent(tick=0, numerator=4, is_default=True, source_input=index)
        events = [*source.meter_map]
    result = [TimingPoint(Fraction(0), _value(default), default)]
    ordered = sorted(
        events, key=lambda event: (event.tick, event.source_track or 0, event.source_event or 0)
    )
    for tick, group in groupby(ordered, key=lambda event: event.tick):
        entries = list(group)
        if len({_value(event) for event in entries}) > 1:
            if not tolerate_conflict:
                raise TimingConflictError(
                    f"Input {index} has conflicting {kind} events at tick {tick}"
                )
            diagnostics.append(
                Diagnostic(
                    code="timing_conflict_overridden",
                    severity="warning",
                    source_input=index,
                    path=source.source,
                    message=f"Ignored input {index}'s conflicting {kind} events "
                    f"at tick {tick}; explicit timing authority selected",
                )
            )
        event = entries[0].model_copy(deep=True)
        event.source_input = index
        point = TimingPoint(Fraction(tick, source.ticks_per_beat), _value(event), event)
        if tick == 0:
            result[0] = point
        elif point.value != result[-1].value:
            result.append(point)
    return result


def resolve_timing_maps(
    inputs: list[ProcessedMidi], result: Arrangement, options: ArrangementOptions
) -> None:
    chosen = options.timing_source if options.timing_source is not None else 0
    for kind in ("tempo", "meter"):
        timelines = [
            _timeline(
                source,
                index,
                kind,
                options.timing_source is not None and index != chosen,
                result.diagnostics,
            )
            for index, source in enumerate(inputs)
        ]
        canonical = timelines[chosen]
        signature = [(point.beat, point.value) for point in canonical]
        for index, timeline in enumerate(timelines):
            if [(point.beat, point.value) for point in timeline] == signature:
                continue
            if options.timing_source is None:
                raise TimingConflictError(
                    f"Effective {kind} maps disagree between inputs {chosen} and {index}; "
                    "select timing_source explicitly to override"
                )
            result.diagnostics.append(
                Diagnostic(
                    code="timing_conflict_overridden",
                    severity="warning",
                    source_input=index,
                    path=inputs[index].source,
                    message=f"Input {index}'s {kind} map overridden by explicit input {chosen}",
                )
            )
        source = inputs[chosen]
        converter = TickConverter(
            result.ticks_per_beat,
            source.ticks_per_beat,
            options.ppq_rounding,
            result.diagnostics,
            source.source,
            chosen,
        )
        previous_tick: int | None = None
        for point in canonical:
            event = point.event.model_copy(deep=True)
            event.tick = converter.convert(
                event.tick, f"{kind} change", event.source_track, event.source_event
            )
            if event.tick == previous_tick:
                raise TimingConflictError(
                    f"PPQ conversion makes distinct {kind} changes collide at tick {event.tick}"
                )
            previous_tick = event.tick
            if isinstance(event, TempoEvent):
                result.tempo_map.append(event)
            else:
                result.meter_map.append(event)
