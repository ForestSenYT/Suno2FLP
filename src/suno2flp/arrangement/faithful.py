"""Faithful beat-aligned arrangements of explicitly selected source note views."""

from math import lcm
from typing import Literal

from suno2flp.arrangement.ppq import TickConverter
from suno2flp.arrangement.timing import resolve_timing_maps
from suno2flp.core.errors import ArrangementError
from suno2flp.core.models import (
    Arrangement,
    ArrangementNoteOrigin,
    ArrangementOptions,
    ArrangementSource,
    ArrangementTrack,
    Diagnostic,
    MusicalMetadata,
    ProcessedMidi,
)


class FaithfulArrangementEngine:
    def arrange(
        self,
        midi: list[ProcessedMidi],
        metadata: MusicalMetadata,
        mode: Literal["faithful", "reinterpretation"] = "faithful",
        *,
        options: ArrangementOptions | None = None,
    ) -> Arrangement:
        if mode != "faithful":
            raise ArrangementError("Only faithful arrangement mode is implemented")
        if not midi:
            raise ArrangementError("At least one MIDI input is required")
        options = ArrangementOptions.model_validate((options or ArrangementOptions()).model_dump())
        if options.timing_source is not None and options.timing_source >= len(midi):
            raise ArrangementError("timing_source must identify an existing input")
        for source in midi:
            _validate_source(source, options)
        target_ppq = options.target_ppq or lcm(*(source.ticks_per_beat for source in midi))
        result = Arrangement(
            ticks_per_beat=target_ppq,
            metadata=metadata.model_copy(deep=True),
            build_options=options.model_copy(deep=True),
        )
        for index, source in enumerate(midi):
            result.sources.append(
                ArrangementSource(
                    input_index=index,
                    note_view="cleaned" if source.cleanup else "imported",
                    midi=source.model_copy(deep=True),
                )
            )
            for diagnostic in source.diagnostics:
                copied = diagnostic.model_copy(deep=True)
                copied.source_input = index
                result.diagnostics.append(copied)
            if source.source_sha256 is None:
                result.diagnostics.append(
                    Diagnostic(
                        code="source_hash_unverified",
                        severity="warning",
                        source_input=index,
                        path=source.source,
                        message="Input has no recorded source hash; no hash fabricated",
                    )
                )
        resolve_timing_maps(midi, result, options)
        for index, source in enumerate(midi):
            converter = TickConverter(
                target_ppq,
                source.ticks_per_beat,
                options.ppq_rounding,
                result.diagnostics,
                source.source,
                index,
            )
            for position, track in enumerate(source.tracks):
                source_track = track.index if track.index is not None else position
                arranged = ArrangementTrack(
                    name=track.name,
                    source=source.source,
                    source_input=index,
                    source_track=source_track,
                    source_track_position=position,
                    source_ticks_per_beat=source.ticks_per_beat,
                    end_tick=converter.convert(track.end_tick, "source track end", source_track),
                )
                for note_index, note in enumerate(track.notes):
                    copied_note = note.model_copy(deep=True)
                    start = converter.convert(
                        note.start_tick, "note start", source_track, note.note_on_event_index
                    )
                    end = converter.convert(
                        note.start_tick + note.duration_ticks,
                        "note end",
                        source_track,
                        note.note_off_event_index,
                    )
                    if note.duration_ticks > 0 and end <= start:
                        raise ArrangementError(
                            "PPQ rounding would collapse a positive note duration"
                        )
                    copied_note.start_tick = start
                    copied_note.duration_ticks = end - start
                    arranged.notes.append(copied_note)
                    arranged.note_origins.append(
                        ArrangementNoteOrigin(
                            note_index=note_index,
                            input_start_tick=note.start_tick,
                            input_duration_ticks=note.duration_ticks,
                        )
                    )
                    arranged.end_tick = max(arranged.end_tick, end)
                result.tracks.append(arranged)
        return result


def _validate_source(source: ProcessedMidi, options: ArrangementOptions) -> None:
    if not source.tracks:
        raise ArrangementError("Input must contain tracks")
    if any(diagnostic.severity == "error" for diagnostic in source.diagnostics):
        raise ArrangementError("Resolve MIDI input errors before arrangement")
    if source.cleanup is not None and options.note_view != "active":
        raise ArrangementError(
            "Cleaned inputs require explicit note_view='active'; use fresh import otherwise"
        )
    for track in source.tracks:
        for note in track.notes:
            if note.original_start_tick is None or note.original_duration_ticks is None:
                raise ArrangementError("Arrangement requires notes with known original timing")
            if source.cleanup is None and (
                note.start_tick != note.original_start_tick
                or note.duration_ticks != note.original_duration_ticks
            ):
                raise ArrangementError(
                    "Unrecorded timing edits require an explicit cleanup provenance record"
                )
