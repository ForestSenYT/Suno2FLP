import hashlib
from pathlib import Path

import mido
import pytest
from pydantic import ValidationError

from suno2flp.core.config import MidiPreferences, load_config
from suno2flp.core.errors import MidiProcessingError, UnsafePathError
from suno2flp.core.models import Asset, Diagnostic, ProcessedMidi
from suno2flp.importer import MidiFileImporter
from suno2flp.midi_processor import DeterministicMidiProcessor


@pytest.fixture
def imported(tmp_path: Path) -> ProcessedMidi:
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks.extend(
        [
            mido.MidiTrack(
                [
                    mido.MetaMessage("track_name", name="Conductor"),
                    mido.MetaMessage("set_tempo", tempo=500000),
                    mido.MetaMessage("time_signature", numerator=4, denominator=4),
                    mido.MetaMessage("set_tempo", tempo=600000, time=960),
                ]
            ),
            mido.MidiTrack(
                [
                    mido.MetaMessage("track_name", name="Piano"),
                    mido.Message("note_on", note=60, velocity=80, time=119),
                    mido.Message("note_on", note=60, velocity=80),
                    mido.Message("control_change", control=64, value=127, time=1),
                    mido.Message("note_off", note=60, time=19),
                    mido.Message("note_off", note=60),
                    mido.Message("note_on", note=62, velocity=70, time=100),
                    mido.Message("note_off", note=62, time=1),
                    mido.Message("note_on", note=64, velocity=90, time=60),
                    mido.Message("note_off", note=64, time=30),
                    mido.MetaMessage("end_of_track", time=100),
                ]
            ),
            mido.MidiTrack([mido.MetaMessage("end_of_track", time=100)]),
        ]
    )
    midi.save(source)
    return MidiFileImporter().import_file(source)


def test_defaults_are_noop_with_independent_source_preserving_result(imported: ProcessedMidi):
    before = imported.model_dump_json()
    result = DeterministicMidiProcessor().clean(imported)
    assert result is not imported
    assert result.tracks == imported.tracks
    assert result.tempo_map == imported.tempo_map and result.meter_map == imported.meter_map
    assert result.cleanup.changes == []
    assert not result.cleanup.options.remove_duplicates and not result.cleanup.options.quantize
    assert imported.cleanup is None and imported.model_dump_json() == before
    result.tracks[1].events[0].message["name"] = "changed copy"
    assert imported.model_dump_json() == before


def test_opt_in_pipeline_records_changes_and_preserves_source(imported: ProcessedMidi):
    processor = DeterministicMidiProcessor()
    options = MidiPreferences(
        remove_duplicates=True, min_duration_ticks=2, quantize=True, quantize_grid_ticks=120
    )
    before = imported.model_dump_json()
    source_hash = hashlib.sha256(imported.source.read_bytes()).hexdigest()
    result = processor.clean(imported, options)
    notes = result.tracks[1].notes
    assert [(n.pitch, n.start_tick, n.duration_ticks) for n in notes] == [
        (60, 120, 20),
        (64, 360, 30),
    ]
    assert [(n.original_start_tick, n.original_duration_ticks) for n in notes] == [
        (119, 20),
        (300, 30),
    ]
    assert [c.operation for c in result.cleanup.changes] == [
        "remove_duplicate_note",
        "remove_short_note",
        "quantize_start",
        "quantize_start",
    ]
    removed = [c for c in result.cleanup.changes if c.after is None]
    assert [(c.track_index, c.note_index, c.before.start_tick) for c in removed] == [
        (1, 1, 119),
        (1, 2, 239),
    ]
    assert removed[0].before.note_on_event_index == 2
    assert all(c.before.original_start_tick is not None for c in result.cleanup.changes)
    assert [t.events for t in result.tracks] == [t.events for t in imported.tracks]
    assert [t.end_tick for t in result.tracks] == [t.end_tick for t in imported.tracks]
    assert result.tempo_map == imported.tempo_map and result.meter_map == imported.meter_map
    assert result.source_sha256 == imported.source_sha256 == source_hash
    assert hashlib.sha256(imported.source.read_bytes()).hexdigest() == source_hash
    assert imported.model_dump_json() == before
    assert processor.clean(imported, options) == result
    assert processor.clean(result, options) == result
    assert ProcessedMidi.model_validate_json(result.model_dump_json()) == result
    assert sum(d.code == "midi_cleanup_applied" for d in result.diagnostics) == 4


def test_each_operation_is_independently_opt_in(imported: ProcessedMidi):
    processor = DeterministicMidiProcessor()
    duplicate_only = processor.clean(imported, MidiPreferences(remove_duplicates=True))
    assert [(n.start_tick, n.duration_ticks) for n in duplicate_only.tracks[1].notes] == [
        (119, 20),
        (239, 1),
        (300, 30),
    ]
    short_only = processor.clean(imported, MidiPreferences(min_duration_ticks=20))
    assert [n.pitch for n in short_only.tracks[1].notes] == [60, 60, 64]
    grid_only = processor.clean(imported, MidiPreferences(quantize=True, quantize_grid_ticks=120))
    assert len(grid_only.tracks[1].notes) == 4
    assert [n.start_tick for n in grid_only.tracks[1].notes] == [120, 120, 240, 360]


def test_duplicate_key_respects_channels_velocities_durations_and_tracks(imported: ProcessedMidi):
    original = imported.tracks[1].notes[0]
    variants = []
    for update in (
        {"channel": 1},
        {"velocity": 81},
        {"duration_ticks": 21, "original_duration_ticks": 21},
        {"start_tick": 120, "original_start_tick": 120},
    ):
        variants.append(original.model_copy(update=update))
    imported.tracks[1].notes.extend(variants)
    imported.tracks[2].notes.append(original.model_copy(deep=True))
    result = DeterministicMidiProcessor().clean(imported, MidiPreferences(remove_duplicates=True))
    assert len(result.tracks[1].notes) == 7
    assert len(result.tracks[2].notes) == 1


def test_quantization_integer_ties_and_large_ticks_do_not_use_float(imported: ProcessedMidi):
    original = imported.tracks[1].notes[0]
    starts = [0, 59, 60, 61, 180, 2**60 + 60]
    imported.tracks[1].notes = [
        original.model_copy(update={"start_tick": start, "original_start_tick": start})
        for start in starts
    ]
    result = DeterministicMidiProcessor().clean(
        imported, MidiPreferences(quantize=True, quantize_grid_ticks=120)
    )
    assert [n.start_tick for n in result.tracks[1].notes] == [
        0,
        0,
        120,
        120,
        240,
        1152921504606847080,
    ]
    assert [n.original_start_tick for n in result.tracks[1].notes] == starts
    assert all(n.duration_ticks == 20 for n in result.tracks[1].notes)


def test_quantization_does_not_trigger_implicit_deduplication(imported: ProcessedMidi):
    note = imported.tracks[1].notes[0]
    imported.tracks[1].notes = [
        note.model_copy(deep=True),
        note.model_copy(update={"start_tick": 120, "original_start_tick": 120}),
    ]
    result = DeterministicMidiProcessor().clean(
        imported, MidiPreferences(remove_duplicates=True, quantize=True, quantize_grid_ticks=120)
    )
    assert len(result.tracks[1].notes) == 2
    assert [n.start_tick for n in result.tracks[1].notes] == [120, 120]


def test_original_timing_is_required_and_changed_preferences_need_fresh_import(imported):
    processor = DeterministicMidiProcessor()
    result = processor.clean(imported, MidiPreferences(remove_duplicates=True))
    with pytest.raises(MidiProcessingError):
        processor.clean(result, MidiPreferences(min_duration_ticks=2))
    imported.tracks[1].notes[0].original_start_tick = None
    with pytest.raises(MidiProcessingError):
        processor.clean(imported, MidiPreferences(remove_duplicates=True))


def test_error_diagnostics_block_cleanup_but_warnings_are_preserved(imported):
    processor = DeterministicMidiProcessor()
    result = processor.clean(imported, MidiPreferences(remove_duplicates=True))
    assert imported.diagnostics[0] in result.diagnostics
    imported.diagnostics.append(Diagnostic(code="bad", severity="error", message="bad input"))
    with pytest.raises(MidiProcessingError):
        processor.clean(imported)


@pytest.mark.parametrize(
    "settings",
    [
        {"min_duration_ticks": -1},
        {"min_duration_ticks": 0.5},
        {"min_duration_ticks": True},
        {"quantize": True},
        {"quantize": True, "quantize_grid_ticks": 0},
        {"quantize": True, "quantize_grid_ticks": 2.5},
        {"quantize_grid_ticks": 120},
        {"preserve_timing": False},
        {"unknown_cleanup": True},
    ],
)
def test_invalid_cleanup_preferences_are_rejected(settings):
    with pytest.raises(ValidationError):
        MidiPreferences(**settings)


def test_config_and_processor_protocol_import_the_real_source(imported, tmp_path):
    config = tmp_path / "project.yaml"
    config.write_text("name: song\nmidi:\n  remove_duplicates: true\n  min_duration_ticks: 2\n")
    preferences = load_config(config).midi
    asset = Asset(path=Path("source.mid"), kind="midi", size_bytes=imported.source.stat().st_size)
    result = DeterministicMidiProcessor().process(asset, tmp_path, preferences)
    assert len(result.tracks[1].notes) == 2
    assert result.source_sha256 == imported.source_sha256
    with pytest.raises(MidiProcessingError):
        DeterministicMidiProcessor().process(
            Asset(path=Path("source.wav"), kind="wav", size_bytes=0), tmp_path, preferences
        )
    escaped = asset.model_copy(update={"path": Path("../outside.mid")})
    with pytest.raises(UnsafePathError):
        DeterministicMidiProcessor().process(escaped, tmp_path, preferences)


def test_release_velocity_distinguishes_notes_for_duplicate_removal(imported):
    second = imported.tracks[1].notes[1]
    imported.tracks[1].events[second.note_off_event_index].message["velocity"] = 20
    result = DeterministicMidiProcessor().clean(imported, MidiPreferences(remove_duplicates=True))
    assert len(result.tracks[1].notes) == 4
    assert result.cleanup.changes == []


def test_zero_length_notes_and_source_end_are_preserved_unless_selected(tmp_path):
    source = tmp_path / "short.mid"
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", note=60, time=60),
                mido.Message("note_off", note=60),
            ]
        )
    )
    midi.save(source)
    imported = MidiFileImporter().import_file(source)
    processor = DeterministicMidiProcessor()
    assert len(processor.clean(imported).tracks[0].notes) == 1
    assert processor.clean(imported, MidiPreferences(min_duration_ticks=1)).tracks[0].notes == []
    result = processor.clean(imported, MidiPreferences(quantize=True, quantize_grid_ticks=120))
    assert result.tracks[0].notes[0].start_tick == 120
    assert result.tracks[0].notes[0].duration_ticks == 0
    assert result.tracks[0].end_tick == imported.tracks[0].end_tick == 60
    snapshot = result.cleanup.changes[0].after
    result.tracks[0].notes[0].start_tick = 240
    assert snapshot.start_tick == 120


def test_missing_release_metadata_prevents_unverified_duplicate_removal(imported):
    imported.tracks[1].notes[1].note_off_event_index = None
    result = DeterministicMidiProcessor().clean(imported, MidiPreferences(remove_duplicates=True))
    assert len(result.tracks[1].notes) == 4
    assert result.cleanup.changes == []
    assert any(d.code == "midi_cleanup_unverified_release" for d in result.diagnostics)


@pytest.mark.parametrize("corruption", ["positive_onset", "channel", "pitch", "tick", "velocity"])
def test_stale_release_metadata_is_not_treated_as_verified(imported, corruption):
    note = imported.tracks[1].notes[1]
    event = imported.tracks[1].events[note.note_off_event_index]
    if corruption == "positive_onset":
        event.message["type"] = "note_on"
    elif corruption == "channel":
        event.message["channel"] = 1
    elif corruption == "pitch":
        event.message["note"] = 61
    elif corruption == "tick":
        event.tick += 1
    else:
        event.message["velocity"] = 128
    result = DeterministicMidiProcessor().clean(imported, MidiPreferences(remove_duplicates=True))
    assert len(result.tracks[1].notes) == 4
    assert result.cleanup.changes == []
    assert any(d.code == "midi_cleanup_unverified_release" for d in result.diagnostics)
