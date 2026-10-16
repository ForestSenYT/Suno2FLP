"""Deterministic transformations of derived notes; source events remain authoritative."""

from pathlib import Path

from suno2flp.core.config import MidiPreferences
from suno2flp.core.errors import MidiProcessingError
from suno2flp.core.models import (
    Asset,
    Diagnostic,
    MidiCleanupChange,
    MidiCleanupOperation,
    MidiCleanupOptions,
    MidiCleanupRecord,
    MidiNote,
    MidiTrack,
    ProcessedMidi,
)
from suno2flp.core.workspace import workspace_path
from suno2flp.importer import MidiFileImporter


class DeterministicMidiProcessor:
    def process(
        self, asset: Asset, source_root: Path, preferences: MidiPreferences
    ) -> ProcessedMidi:
        """Implement MidiProcessor by freshly importing a contained MIDI asset."""
        if asset.kind != "midi":
            raise MidiProcessingError("MIDI cleanup requires a MIDI asset")
        source = workspace_path(source_root, asset.path)
        return self.clean(MidiFileImporter().import_file(source), preferences)

    def clean(
        self, midi: ProcessedMidi, preferences: MidiPreferences | None = None
    ) -> ProcessedMidi:
        """Return an independent derived view plus audit; default options change no notes.

        A recorded result can be reused with identical preferences. To change the
        pipeline, start again from its original import instead of stacking lossy edits.
        """
        options = MidiCleanupOptions.model_validate(
            (preferences if preferences is not None else MidiPreferences()).model_dump()
        )
        if any(diagnostic.severity == "error" for diagnostic in midi.diagnostics):
            raise MidiProcessingError("Resolve MIDI import errors before cleanup")
        if midi.cleanup is not None:
            if midi.cleanup.options == options:
                return midi.model_copy(deep=True)
            raise MidiProcessingError(
                "Changed cleanup options require a fresh original MIDI import"
            )
        for track in midi.tracks:
            for note in track.notes:
                if (
                    note.original_start_tick != note.start_tick
                    or note.original_duration_ticks != note.duration_ticks
                ):
                    raise MidiProcessingError(
                        "Cleanup requires unmodified notes with original timing"
                    )
        result = midi.model_copy(deep=True)
        record = MidiCleanupRecord(options=options)
        for position, track in enumerate(result.tracks):
            track_index = track.index if track.index is not None else position
            seen: set[tuple[int, int, int, int, int, int | None]] = set()
            kept: list[tuple[int, MidiNote]] = []
            for note_index, note in enumerate(track.notes):
                if note.duration_ticks < options.min_duration_ticks:
                    _record_change(
                        result, record, "remove_short_note", track_index, note_index, note
                    )
                    continue
                release = _release_velocity(track, note)
                key = (
                    note.channel,
                    note.pitch,
                    note.velocity,
                    note.start_tick,
                    note.duration_ticks,
                    release,
                )
                if options.remove_duplicates and release is not None and key in seen:
                    _record_change(
                        result, record, "remove_duplicate_note", track_index, note_index, note
                    )
                    continue
                if options.remove_duplicates and release is None:
                    result.diagnostics.append(
                        Diagnostic(
                            code="midi_cleanup_unverified_release",
                            severity="warning",
                            message=f"Note {note_index}: no release data; dedup skipped",
                            path=result.source,
                            track_index=track_index,
                            event_index=note.note_on_event_index,
                        )
                    )
                seen.add(key)
                kept.append((note_index, note))
            for note_index, note in kept:
                if options.quantize and options.quantize_grid_ticks is not None:
                    grid = options.quantize_grid_ticks
                    # Nearest tick-grid point, exact half-grid ties toward the later tick.
                    quantized = ((2 * note.start_tick + grid) // (2 * grid)) * grid
                    if quantized != note.start_tick:
                        before = note.model_copy(deep=True)
                        note.start_tick = quantized
                        _record_change(
                            result, record, "quantize_start", track_index, note_index, before, note
                        )
            track.notes = [note for _, note in kept]
        result.cleanup = record
        return result


def _release_velocity(track: MidiTrack, note: MidiNote) -> int | None:
    index = note.note_off_event_index
    if index is None or index >= len(track.events):
        return None
    event = track.events[index]
    if event.event_index != index or event.tick != note.start_tick + note.duration_ticks:
        return None
    value = event.message.get("velocity")
    if type(value) is not int or not 0 <= value <= 127:
        return None
    kind = event.message.get("type")
    if kind != "note_off" and not (kind == "note_on" and value == 0):
        return None
    channel, pitch = event.message.get("channel"), event.message.get("note")
    if type(channel) is not int or type(pitch) is not int:
        return None
    if channel != note.channel or pitch != note.pitch:
        return None
    return value


def _record_change(
    result: ProcessedMidi,
    record: MidiCleanupRecord,
    operation: MidiCleanupOperation,
    track_index: int,
    note_index: int,
    before: MidiNote,
    after: MidiNote | None = None,
) -> None:
    record.changes.append(
        MidiCleanupChange(
            operation=operation,
            track_index=track_index,
            note_index=note_index,
            before=before.model_copy(deep=True),
            after=after.model_copy(deep=True) if after is not None else None,
        )
    )
    result.diagnostics.append(
        Diagnostic(
            code="midi_cleanup_applied",
            severity="info",
            message=f"{operation}: imported note {note_index}",
            path=result.source,
            track_index=track_index,
            event_index=before.note_on_event_index,
        )
    )
