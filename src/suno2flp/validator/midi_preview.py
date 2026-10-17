"""Independently decode complete SMF framing/messages against the projected score."""

import struct
from io import BytesIO

import mido

from suno2flp.arrangement.midi_preview import project_estimated_midi
from suno2flp.core.estimated_midi import EstimatedMidiScore

MidiStream = list[tuple[int, dict[str, str | int]]]


def _vlq(raw: bytes, cursor: int, end: int) -> tuple[int, int]:
    value = 0
    for count in range(4):
        if cursor >= end:
            raise ValueError("Truncated MIDI variable-length quantity")
        byte = raw[cursor]
        cursor += 1
        if count == 0 and byte == 0x80:
            raise ValueError("Noncanonical MIDI variable-length quantity")
        value = value * 128 + (byte & 127)
        if byte < 128:
            return value, cursor
    raise ValueError("MIDI variable-length quantity exceeds four bytes")


def _track_bytes(raw: bytes, cursor: int, end: int) -> None:
    running: int | None = None
    while cursor < end:
        _, cursor = _vlq(raw, cursor, end)
        if cursor == end:
            raise ValueError("MIDI delta lacks an event")
        status = raw[cursor]
        if status >= 128:
            cursor += 1
        elif running is not None:
            status = running
        else:
            raise ValueError("MIDI data lacks a channel status")
        if status == 0xFF:
            running = None
            if cursor == end:
                raise ValueError("Truncated MIDI meta type")
            kind = raw[cursor]
            size, cursor = _vlq(raw, cursor + 1, end)
            if cursor + size > end:
                raise ValueError("Truncated MIDI meta payload")
            if kind not in (3, 0x2F, 0x51) or (kind == 0x51 and size != 3):
                raise ValueError("Unexpected MIDI preview metadata or payload size")
            if kind == 0x2F:
                if size != 0 or cursor != end:
                    raise ValueError("MIDI end-of-track must be empty and final")
                return
            cursor += size
        else:
            if status >> 4 not in (8, 9) or cursor + 2 > end:
                raise ValueError("Unexpected or truncated MIDI preview channel event")
            if any(byte >= 128 for byte in raw[cursor : cursor + 2]):
                raise ValueError("MIDI note data must use seven-bit bytes")
            running = status
            cursor += 2
    raise ValueError("MIDI track lacks an explicit end-of-track")


def verify_estimated_midi(raw: bytes, score: EstimatedMidiScore) -> None:
    if score != project_estimated_midi(score.arrangement):
        raise ValueError("Estimated MIDI score changed from its source projection")
    if len(raw) > 8 * 1024**2 or len(raw) < 14:
        raise ValueError("MIDI must retain the complete bounded SMF")
    if raw[:4] != b"MThd" or struct.unpack(">IHHH", raw[4:14]) != (6, 1, 5, 960):
        raise ValueError("Unexpected MIDI header or technical clock")
    cursor = 14
    for _ in range(5):
        if cursor + 8 > len(raw) or raw[cursor : cursor + 4] != b"MTrk":
            raise ValueError("Missing complete MIDI track framing")
        size = int.from_bytes(raw[cursor + 4 : cursor + 8], "big")
        cursor += 8 + size
        if cursor > len(raw):
            raise ValueError("Truncated MIDI track")
        _track_bytes(raw, cursor - size, cursor)
    if cursor != len(raw):
        raise ValueError("Unexpected trailing MIDI bytes")
    midi = mido.MidiFile(file=BytesIO(raw))
    conductor: MidiStream = [
        (0, dict(type="track_name", name="Unqualified audio inference - technical clock")),
        (0, dict(type="set_tempo", tempo=500000)),
        (score.end_tick, dict(type="end_of_track")),
    ]
    expected_tracks: list[MidiStream] = [conductor]
    for part in score.parts:
        expected: MidiStream = [(0, dict(type="track_name", name=part.stem))]
        notes: list[tuple[int, int, int, dict[str, str | int]]] = []
        for index, note in enumerate(part.notes):
            notes.append(
                (
                    note.start.tick,
                    1,
                    index,
                    dict(type="note_on", channel=part.channel, note=note.pitch, velocity=96),
                )
            )
            notes.append(
                (
                    note.end.tick,
                    0,
                    index,
                    dict(type="note_off", channel=part.channel, note=note.pitch, velocity=0),
                )
            )
        expected += [(t, msg) for t, _, _, msg in sorted(notes, key=lambda n: n[:3])]
        expected.append((score.end_tick, dict(type="end_of_track")))
        expected_tracks.append(expected)
    for track, expected in zip(midi.tracks, expected_tracks, strict=True):
        actual = []
        tick = 0
        for message in track:
            if not isinstance(message.time, int) or message.time < 0:
                raise ValueError("MIDI delta must be an exact nonnegative integer")
            tick += message.time
            payload = message.dict()
            payload.pop("time")
            actual.append((tick, payload))
        if actual != expected:
            raise ValueError("Complete MIDI events or timing differ from the audited score")
