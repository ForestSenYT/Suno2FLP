"""Independent complete note-only SMF decoding; no backend or writer authority."""

from io import BytesIO

import mido

from suno2flp.core.moe_midi import MoEMidiPart
from suno2flp.validator.smf_notes import MidiStream, verify_note_smf


def verify_moe_part(raw: bytes, part: MoEMidiPart, end_tick: int) -> None:
    part = MoEMidiPart.model_validate_json(part.model_dump_json())
    if (
        type(end_tick) is not int
        or not 0 <= end_tick <= 2**31 - 1
        or any(note.end.tick > end_tick for note in part.notes)
    ):
        raise ValueError("MIDI source end cannot truncate any note")
    verify_note_smf(raw, tracks=2)
    expected: list[MidiStream] = [
        [
            (0, dict(type="track_name", name="Unqualified MoE inference - technical clock")),
            (0, dict(type="set_tempo", tempo=500000)),
            (end_tick, dict(type="end_of_track")),
        ]
    ]
    label = f"model-channel={part.source_channel:02d};model-program={part.model_program:03d}"
    notes: MidiStream = [(0, dict(type="track_name", name=label))]
    events: list[tuple[int, int, int, dict[str, str | int]]] = []
    for note in part.notes:
        for tick, priority, kind, velocity in (
            (note.start.tick, 1, "note_on", 96),
            (note.end.tick, 0, "note_off", 0),
        ):
            events.append(
                (
                    tick,
                    priority,
                    note.source_index,
                    dict(
                        type=kind,
                        channel=part.midi_channel,
                        note=note.native.pitch,
                        velocity=velocity,
                    ),
                )
            )
    notes += [(tick, msg) for tick, _, _, msg in sorted(events, key=lambda n: n[:3])]
    notes.append((end_tick, dict(type="end_of_track")))
    expected.append(notes)
    midi = mido.MidiFile(file=BytesIO(raw))
    for track, required in zip(midi.tracks, expected, strict=True):
        actual = []
        tick = 0
        for message in track:
            tick += message.time
            payload = message.dict()
            payload.pop("time")
            actual.append((tick, payload))
        if actual != required:
            raise ValueError("Complete model-program MIDI events differ from native projection")
