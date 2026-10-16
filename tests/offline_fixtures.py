"""Small original MIDI fixtures shared by offline quality/workflow tests."""

from pathlib import Path

import mido

from suno2flp.arrangement import FaithfulArrangementEngine
from suno2flp.core.models import ArrangementOptions, MusicalMetadata
from suno2flp.importer import MidiFileImporter


def write_midi(path: Path, *, ppq=480, start=120, duration=240, tempo=500000):
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)
    midi.tracks = [
        mido.MidiTrack(
            [
                mido.MetaMessage("set_tempo", tempo=tempo),
                mido.MetaMessage("time_signature", numerator=4, denominator=4),
                mido.MetaMessage("end_of_track"),
            ]
        ),
        mido.MidiTrack(
            [
                mido.MetaMessage("track_name", name="Original synthetic"),
                mido.Message("note_on", channel=2, note=60, velocity=90, time=start),
                mido.Message("note_off", channel=2, note=60, velocity=30, time=duration),
                mido.MetaMessage("end_of_track"),
            ]
        ),
    ]
    midi.save(path)
    return MidiFileImporter().import_file(path)


def arrangement_file(root: Path, *, options: ArrangementOptions | None = None):
    imported = write_midi(root / "source.mid")
    arrangement = FaithfulArrangementEngine().arrange(
        [imported],
        MusicalMetadata(title="Synthetic"),
        options=options,
    )
    path = root / "arrangement.json"
    path.write_text(arrangement.model_dump_json(indent=2), encoding="utf-8")
    return path, arrangement, imported
