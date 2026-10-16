"""Read-only, track-aware Standard MIDI import. No cleanup or seconds conversion."""

import hashlib
import io
import json
import struct
from collections import defaultdict, deque
from collections.abc import Iterable
from itertools import groupby
from pathlib import Path
from typing import Any

import mido
from mido.midifiles.meta import KeySignatureError

from suno2flp.core.errors import MidiImportError
from suno2flp.core.models import (
    Diagnostic,
    MeterEvent,
    MidiEvent,
    MidiNote,
    MidiTrack,
    ProcessedMidi,
    TempoEvent,
)
from suno2flp.importer._midi_timing import source_deltas


class MidiFileImporter:
    def import_file(self, source: Path) -> ProcessedMidi:
        """Decode Type 0/1 PPQ MIDI, preserving ticks, track/event order and provenance.

        Maps contain source events only. Consumers apply MIDI's 500000 us/beat and
        4/4 defaults before the first explicit changes. Same-tick conflicts remain
        present in stable track/event order and produce diagnostics.
        """
        try:
            source = source.resolve()
            raw = source.read_bytes()
            midi = mido.MidiFile(file=io.BytesIO(raw), clip=False)
            if midi.type == 2:
                raise MidiImportError(
                    "Type 2 MIDI has independent timelines; import is unsupported"
                )
            if midi.ticks_per_beat <= 0:
                raise MidiImportError(
                    "Positive PPQ is required; SMPTE/zero divisions are unsupported"
                )
            if not midi.tracks or (midi.type == 0 and len(midi.tracks) != 1):
                raise MidiImportError("MIDI must have tracks; Type 0 must have exactly one track")
            # mido 1.3.3 drops deltas on unknown meta events. Restore from source
            # framing only when needed; keep decoder state local to this import.
            if any(message.type == "unknown_meta" for track in midi.tracks for message in track):
                deltas = source_deltas(raw)
                for track, track_deltas in zip(midi.tracks, deltas, strict=True):
                    for message, delta in zip(track, track_deltas, strict=True):
                        message.time = delta
            result = ProcessedMidi(
                source=source,
                source_sha256=hashlib.sha256(raw).hexdigest(),
                format=midi.type,
                ticks_per_beat=midi.ticks_per_beat,
            )
            for index, messages in enumerate(midi.tracks):
                result.tracks.append(_import_track(messages, index, result))
            _order_maps(result)
            return result
        except MidiImportError:
            raise
        except (
            OSError,
            RuntimeError,
            EOFError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            struct.error,
            KeySignatureError,
        ) as exc:
            raise MidiImportError(f"Cannot import MIDI {source}: {exc}") from exc


def _diagnose(
    result: ProcessedMidi,
    code: str,
    message: str,
    track: int,
    event: int,
    *,
    error: bool = False,
) -> None:
    result.diagnostics.append(
        Diagnostic(
            code=code,
            severity="error" if error else "warning",
            message=message,
            path=result.source,
            track_index=track,
            event_index=event,
        )
    )


def _import_track(messages: Iterable[Any], index: int, result: ProcessedMidi) -> MidiTrack:
    track = MidiTrack(name=f"Track {index + 1}", index=index)
    named = False
    tick = 0
    # MIDI does not identify overlapping voices of the same channel/pitch. FIFO is
    # deterministic, and the diagnostic marks this interpretation as ambiguous.
    active: dict[tuple[int, int], deque[tuple[int, int, int]]] = defaultdict(deque)
    for event_index, message in enumerate(messages):
        tick += message.time
        track.events.append(
            MidiEvent(
                event_index=event_index,
                tick=tick,
                delta_ticks=message.time,
                message=json.loads(json.dumps(message.dict())),
            )
        )
        if message.type == "track_name" and not named and message.name:
            track.name = message.name
            named = True
        elif message.type == "set_tempo":
            if message.tempo > 0:
                result.tempo_map.append(
                    TempoEvent(
                        tick=tick,
                        microseconds_per_beat=message.tempo,
                        source_track=index,
                        source_event=event_index,
                    )
                )
            else:
                _diagnose(
                    result,
                    "invalid_tempo",
                    "Tempo must be positive; raw event retained",
                    index,
                    event_index,
                    error=True,
                )
        elif message.type == "time_signature":
            if message.numerator > 0:
                result.meter_map.append(
                    MeterEvent(
                        tick=tick,
                        numerator=message.numerator,
                        denominator=message.denominator,
                        clocks_per_click=message.clocks_per_click,
                        notated_32nd_notes_per_beat=message.notated_32nd_notes_per_beat,
                        source_track=index,
                        source_event=event_index,
                    )
                )
            else:
                _diagnose(
                    result,
                    "invalid_meter",
                    "Meter numerator must be positive; raw event retained",
                    index,
                    event_index,
                    error=True,
                )
        elif message.type in {"note_on", "note_off"}:
            key = (message.channel, message.note)
            if message.type == "note_on" and message.velocity > 0:
                if active[key]:
                    _diagnose(
                        result,
                        "overlapping_note",
                        f"Overlapping channel/pitch {key}; note releases paired FIFO",
                        index,
                        event_index,
                    )
                active[key].append((tick, message.velocity, event_index))
            elif active[key]:
                start, velocity, onset_index = active[key].popleft()
                duration = tick - start
                track.notes.append(
                    MidiNote(
                        pitch=message.note,
                        channel=message.channel,
                        velocity=velocity,
                        start_tick=start,
                        duration_ticks=duration,
                        original_start_tick=start,
                        original_duration_ticks=duration,
                        note_on_event_index=onset_index,
                        note_off_event_index=event_index,
                    )
                )
            else:
                _diagnose(
                    result,
                    "unmatched_note_off",
                    f"No track-local note-on for {key}",
                    index,
                    event_index,
                )
    for key, pending in active.items():
        for start, _, event_index in pending:
            _diagnose(
                result,
                "unclosed_note",
                f"No note release for {key} at tick {start}; duration not invented",
                index,
                event_index,
            )
    track.notes.sort(key=lambda note: note.note_on_event_index or 0)
    track.end_tick = tick
    return track


def _order_maps(result: ProcessedMidi) -> None:
    result.tempo_map.sort(key=lambda event: (event.tick, event.source_track, event.source_event))
    result.meter_map.sort(key=lambda event: (event.tick, event.source_track, event.source_event))
    for tick, tempos in groupby(result.tempo_map, key=lambda event: event.tick):
        events = list(tempos)
        if len({event.microseconds_per_beat for event in events}) > 1:
            last = events[-1]
            _diagnose(
                result,
                "conflicting_tempo",
                f"Different tempos at tick {tick}; all source events retained",
                last.source_track or 0,
                last.source_event or 0,
            )
    for tick, meters in groupby(result.meter_map, key=lambda event: event.tick):
        entries = list(meters)
        if (
            len(
                {
                    (
                        event.numerator,
                        event.denominator,
                        event.clocks_per_click,
                        event.notated_32nd_notes_per_beat,
                    )
                    for event in entries
                }
            )
            > 1
        ):
            last_meter = entries[-1]
            _diagnose(
                result,
                "conflicting_meter",
                f"Different meters at tick {tick}; all source events retained",
                last_meter.source_track or 0,
                last_meter.source_event or 0,
            )
