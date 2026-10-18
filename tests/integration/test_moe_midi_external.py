"""Opt-in existing current MoE producer: actual token replay and independent MIDI import."""

import os
from pathlib import Path

import pytest

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.importer.midi import MidiFileImporter
from suno2flp.pipeline.moe_midi import export_moe_midi, verify_moe_midi_export


@pytest.mark.external
def test_current_moe_producer_to_program_midi_files(tmp_path):
    value = os.environ.get("SUNO2FLP_MOE_MIDI_PRODUCER")
    if not value:
        pytest.skip("Set SUNO2FLP_MOE_MIDI_PRODUCER to a separately qualified current MoE report")
    path = Path(value)
    if not path.is_file():
        pytest.skip("MoE producer report prerequisite is missing")
    before = capture_stream_input(path)
    record = export_moe_midi(path, tmp_path / "new inferred MIDI")
    assert verify_moe_midi_export(record.root / "moe-midi.json") == record
    total = 0
    for part, output in zip(record.score.parts, record.files, strict=True):
        imported = MidiFileImporter().import_file(output.midi.path)
        assert imported.ticks_per_beat == 960 and imported.format == 1
        assert not imported.diagnostics and not imported.meter_map
        assert len(imported.tempo_map) == 1
        assert imported.tempo_map[0].microseconds_per_beat == 500000
        assert len(imported.tracks) == 2 and not imported.tracks[0].notes
        expected = sorted(
            (n.native.pitch, n.start.tick, n.end.tick - n.start.tick, 96, part.midi_channel)
            for n in part.notes
        )
        actual = sorted(
            (n.pitch, n.start_tick, n.duration_ticks, n.velocity, n.channel)
            for n in imported.tracks[1].notes
        )
        assert actual == expected
        assert all(t.end_tick == record.score.end_tick for t in imported.tracks)
        total += len(actual)
    assert total == sum(len(c.notes) for c in record.score.inputs.model_channels)
    assert record.score.writer_eligibility == "blocked" and not record.score.execution_allowed
    assert capture_stream_input(path) == before
