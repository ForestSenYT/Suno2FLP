"""Independently decode complete SMF framing/messages against the projected score."""

from io import BytesIO

import mido

from suno2flp.arrangement.midi_preview import project_estimated_midi
from suno2flp.core.estimated_midi import EstimatedMidiScore
from suno2flp.validator.smf_notes import MidiStream, verify_note_smf


def verify_estimated_midi(raw: bytes, score: EstimatedMidiScore) -> None:
    if score != project_estimated_midi(score.arrangement):
        raise ValueError("Estimated MIDI score changed from its source projection")
    verify_note_smf(raw, tracks=5)
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
