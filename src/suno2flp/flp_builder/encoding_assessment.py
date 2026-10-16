"""Read-only encoding analysis, separate from every writer authorization path."""

from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from suno2flp.core.encoding_assessment import (
    EncodingAssessment,
    SignedRatio,
    SourceRoute,
    TempoPrecision,
    UnroutedControl,
)
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.models import Diagnostic
from suno2flp.core.offline_files import capture_input, load_unique_json, verify_inputs
from suno2flp.core.performance import PerformanceEventAddress, PerformancePlan, RationalTime
from suno2flp.flp_builder.performance import verify_performance_file


def _fraction(value: RationalTime) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _precision(
    plan: PerformancePlan,
) -> tuple[list[TempoPrecision], SignedRatio | None, SignedRatio | None]:
    end = max((_fraction(track.end.target_tick) for track in plan.tracks), default=Fraction(0))
    tempos = []
    cumulative = Fraction(0)
    maximum = Fraction(0)
    complete = True
    for index, tempo in enumerate(plan.tempos):
        scalar = _fraction(tempo.milli_bpm)
        # Counterfactual only: nearest integer, exact ties choose the lower integer.
        floor = scalar.numerator // scalar.denominator
        nearest = floor + int(scalar - floor > Fraction(1, 2))
        candidate = nearest if 60000 <= scalar <= 240000 else None
        error = (
            None
            if candidate is None
            else Fraction(60_000_000_000, candidate) - tempo.source.microseconds_per_beat
        )
        tempos.append(
            TempoPrecision(
                source=tempo.model_copy(deep=True),
                exact=scalar.denominator == 1,
                hypothetical_nearest_millibpm=candidate,
                period_error_microseconds=None if error is None else SignedRatio.exact(error),
            )
        )
        if error is None:
            complete = False
        else:
            stop = (
                _fraction(plan.tempos[index + 1].position.target_tick)
                if index + 1 < len(plan.tempos)
                else end
            )
            beats = (stop - _fraction(tempo.position.target_tick)) / plan.target_ppq
            cumulative += beats * error
            maximum = max(maximum, abs(cumulative))
    return (
        tempos,
        SignedRatio.exact(cumulative) if complete else None,
        SignedRatio.exact(maximum) if complete else None,
    )


def _routes(plan: PerformancePlan) -> tuple[list[SourceRoute], list[UnroutedControl], list[int]]:
    routes: dict[tuple[int, int], SourceRoute] = {}
    nonchannel: list[UnroutedControl] = []
    addresses = {
        (e.source_input, e.source_track_position, e.source_event_index): e
        for e in plan.untranslated_events
    }
    sources = {s.input_index: s for s in plan.arrangement.sources}
    for timed_track in plan.tracks:
        source = sources[timed_track.source_input]
        track = source.midi.tracks[timed_track.source_track_position]
        for event, timed_event in zip(track.events, timed_track.events, strict=True):
            channel = event.message.get("channel")
            group = None
            if type(channel) is int:
                key = (source.input_index, channel)
                if key not in routes:
                    routes[key] = SourceRoute(
                        source_input=source.input_index,
                        source_channel=channel,
                        source_track_positions=[],
                        channel_event_count=0,
                        controls=[],
                        cross_track_same_tick_groups=[],
                    )
                group = routes[key]
                if timed_track.source_track_position not in group.source_track_positions:
                    group.source_track_positions.append(timed_track.source_track_position)
                group.channel_event_count += 1
            address = addresses.get(
                (source.input_index, timed_track.source_track_position, event.event_index)
            )
            if address is not None:
                control = UnroutedControl(
                    address=address.model_copy(deep=True),
                    source_tick=event.tick,
                    delta_ticks=event.delta_ticks,
                    position=timed_event.position.model_copy(deep=True),
                    message=event.model_copy(deep=True).message,
                )
                (nonchannel if group is None else group.controls).append(control)
    channels: dict[int, set[int]] = defaultdict(set)
    result = [routes[key] for key in sorted(routes)]
    for route in result:
        channels[route.source_channel].add(route.source_input)
        at_tick: dict[int, list[PerformanceEventAddress]] = defaultdict(list)
        for control in route.controls:
            at_tick[control.source_tick].append(control.address.model_copy(deep=True))
        route.cross_track_same_tick_groups = [
            group
            for _, group in sorted(at_tick.items())
            if len({address.source_track_position for address in group}) > 1
        ]
    return (
        result,
        nonchannel,
        sorted(channel for channel, inputs in channels.items() if len(inputs) > 1),
    )


def assess_encoding_file(performance_file: Path) -> EncodingAssessment:
    identity, _ = capture_input(performance_file)
    plan = verify_performance_file(performance_file)
    tempos, end_error, maximum = _precision(plan)
    routes, nonchannel, reused = _routes(plan)
    report = EncodingAssessment(
        performance_file=identity,
        performance_fingerprint=snapshot_sha256(plan),
        input_files=[identity, *plan.input_files],
        referenced_paths=[identity.path, *plan.referenced_paths],
        tempos=tempos,
        hypothetical_end_error_microseconds=end_error,
        maximum_boundary_error_microseconds=maximum,
        routes=routes,
        reused_source_channels=reused,
        nonchannel_events=nonchannel,
        diagnostics=[d.model_copy(deep=True) for d in plan.diagnostics]
        + [
            Diagnostic(
                code="encoding_step_timing_unverified",
                severity="error",
                message=(
                    "Event-223 background probes show step timing differences; "
                    "no source tick compensation is permitted"
                ),
            ),
            Diagnostic(
                code="encoding_destination_unverified",
                severity="error",
                message=(
                    "Every source input/channel needs an explicit instrument/port route; "
                    "native channel volume is not MIDI CC7"
                ),
            ),
        ],
    )
    verify_inputs(report.input_files)
    return report


def verify_encoding_file(path: Path) -> EncodingAssessment:
    identity, raw = capture_input(path)
    saved = EncodingAssessment.model_validate(load_unique_json(raw))
    rebuilt = assess_encoding_file(saved.performance_file.path)
    if saved != rebuilt:
        raise ValueError("Encoding assessment replay mismatch")
    verify_inputs([identity, *rebuilt.input_files])
    return rebuilt
