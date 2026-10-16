import hashlib
from pathlib import Path

import mido
import pytest
from pydantic import ValidationError

from suno2flp.arrangement import FaithfulArrangementEngine
from suno2flp.core.config import MidiPreferences
from suno2flp.core.errors import ArrangementError, TimingConflictError
from suno2flp.core.models import (
    Arrangement,
    ArrangementOptions,
    Diagnostic,
    MusicalMetadata,
)
from suno2flp.importer import MidiFileImporter
from suno2flp.midi_processor import DeterministicMidiProcessor
from suno2flp.validator import LocalQualityValidator


def make_input(
    tmp_path, name="one", *, ppq=480, start=119, duration=241, tempos=(), meters=(), trailing=40
):
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)
    conductor = mido.MidiTrack([mido.MetaMessage("track_name", name="Conductor")])
    events = [(tick, mido.MetaMessage("set_tempo", tempo=value)) for tick, value in tempos]
    events.extend(
        (tick, mido.MetaMessage("time_signature", numerator=n, denominator=d))
        for tick, n, d in meters
    )
    previous = 0
    for tick, message in sorted(events, key=lambda item: item[0]):
        conductor.append(message.copy(time=tick - previous))
        previous = tick
    midi.tracks.extend(
        [
            conductor,
            mido.MidiTrack(
                [
                    mido.MetaMessage("track_name", name="Piano"),
                    mido.Message("program_change", channel=2, program=10),
                    mido.Message("note_on", channel=2, note=60, velocity=80, time=start),
                    mido.Message("note_off", channel=2, note=60, time=duration),
                    mido.MetaMessage("end_of_track", time=trailing),
                ]
            ),
            mido.MidiTrack([mido.MetaMessage("end_of_track", time=5)]),
        ]
    )
    source = tmp_path / f"{name}.mid"
    midi.save(source)
    return MidiFileImporter().import_file(source)


def test_faithful_same_ppq_preserves_notes_tracks_provenance_and_inputs(tmp_path: Path):
    midi = make_input(tmp_path, tempos=[(0, 500000), (480, 600000)], meters=[(0, 4, 4)])
    before = midi.model_dump_json()
    raw = midi.source.read_bytes()
    metadata = MusicalMetadata(title="Faithful")
    result = FaithfulArrangementEngine().arrange([midi], metadata, "faithful")
    assert result.ticks_per_beat == 480 and result.mode == "faithful"
    assert [t.name for t in result.tracks] == ["Conductor", "Piano", "Track 3"]
    assert [t.end_tick for t in result.tracks] == [480, 400, 5]
    track = result.tracks[1]
    assert track.source_input == 0 and track.source_track == 1
    assert track.source_track_position == 1 and track.source_ticks_per_beat == 480
    assert track.notes == midi.tracks[1].notes
    assert track.note_origins[0].note_index == 0
    assert track.note_origins[0].input_start_tick == 119
    assert track.note_origins[0].input_duration_ticks == 241
    assert result.sources[0].midi == midi and result.sources[0].note_view == "imported"
    assert result.sources[0].midi.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.tempo_map[1].source_input == 0
    assert result.tempo_map[1].source_track == 0
    assert result.tempo_map[1].tick == 480
    assert result.build_options == ArrangementOptions()
    assert Arrangement.model_validate_json(result.model_dump_json()) == result
    assert FaithfulArrangementEngine().arrange([midi], metadata, "faithful") == result
    assert LocalQualityValidator().validate_arrangement(result, 3, 2).valid
    result.sources[0].midi.tracks[1].events[0].message["name"] = "changed"
    result.tracks[1].notes[0].start_tick = 999
    result.metadata.title = "changed"
    assert midi.model_dump_json() == before and metadata.title == "Faithful"
    assert midi.source.read_bytes() == raw


def test_mixed_ppq_defaults_to_exact_lcm_and_retains_original_units(tmp_path):
    first = make_input(tmp_path, ppq=480, start=120, duration=240, tempos=[(480, 600000)])
    second = make_input(tmp_path, "two", ppq=720, start=180, duration=360, tempos=[(720, 600000)])
    result = FaithfulArrangementEngine().arrange([first, second], MusicalMetadata(), "faithful")
    assert result.ticks_per_beat == 1440
    for index in (1, 4):
        assert (
            result.tracks[index].notes[0].start_tick,
            result.tracks[index].notes[0].duration_ticks,
        ) == (360, 720)
    assert result.tracks[1].notes[0].original_start_tick == 120
    assert result.tracks[4].notes[0].original_start_tick == 180
    assert result.tracks[4].source_ticks_per_beat == 720
    assert [(e.tick, e.microseconds_per_beat) for e in result.tempo_map] == [
        (0, 500000),
        (1440, 600000),
    ]
    assert not any(d.code == "ppq_rounded" for d in result.diagnostics)


def test_explicit_exact_ppq_and_defaults_have_explicit_origin(tmp_path):
    midi = make_input(tmp_path, start=120, duration=240, trailing=0)
    midi.tracks[2].end_tick = 0
    result = FaithfulArrangementEngine().arrange(
        [midi], MusicalMetadata(), "faithful", options=ArrangementOptions(target_ppq=960)
    )
    assert result.tracks[1].notes[0].start_tick == 240
    assert result.tracks[1].notes[0].duration_ticks == 480
    assert result.tempo_map[0].is_default and result.meter_map[0].is_default
    assert result.tempo_map[0].source_event is None
    assert not result.sources[0].midi.tempo_map


def test_inexact_ppq_rejected_by_default_and_endpoint_rounding_is_explicit(tmp_path):
    midi = make_input(tmp_path, ppq=3, start=1, duration=1, trailing=0)
    midi.tracks[2].end_tick = 0
    engine = FaithfulArrangementEngine()
    with pytest.raises(ArrangementError, match="exact|PPQ"):
        engine.arrange(
            [midi], MusicalMetadata(), "faithful", options=ArrangementOptions(target_ppq=2)
        )
    with pytest.raises(ArrangementError, match="collapse|duration"):
        engine.arrange(
            [midi],
            MusicalMetadata(),
            "faithful",
            options=ArrangementOptions(target_ppq=2, ppq_rounding="nearest"),
        )
    # At 3->4 PPQ, independent endpoints 1->1 and 2->3 give duration 2.
    result = engine.arrange(
        [midi],
        MusicalMetadata(),
        "faithful",
        options=ArrangementOptions(target_ppq=4, ppq_rounding="nearest"),
    )
    note = result.tracks[1].notes[0]
    assert (note.start_tick, note.duration_ticks) == (1, 2)
    assert note.original_start_tick == note.original_duration_ticks == 1
    assert any(d.code == "ppq_rounded" for d in result.diagnostics)


def test_rounding_cannot_collapse_a_positive_note(tmp_path):
    midi = make_input(tmp_path, ppq=480, start=1, duration=1, trailing=0)
    midi.tracks[2].end_tick = 0
    with pytest.raises(ArrangementError, match="collapse|duration"):
        FaithfulArrangementEngine().arrange(
            [midi],
            MusicalMetadata(),
            "faithful",
            options=ArrangementOptions(target_ppq=1, ppq_rounding="nearest"),
        )


def test_active_view_requires_explicit_selection_and_keeps_cleanup_audit(tmp_path):
    imported = make_input(tmp_path, duration=1)
    cleaned = DeterministicMidiProcessor().clean(imported, MidiPreferences(min_duration_ticks=2))
    engine = FaithfulArrangementEngine()
    with pytest.raises(ArrangementError, match="active|cleaned|view"):
        engine.arrange([cleaned], MusicalMetadata(), "faithful")
    result = engine.arrange(
        [imported, cleaned],
        MusicalMetadata(),
        "faithful",
        options=ArrangementOptions(note_view="active"),
    )
    assert len(result.tracks[1].notes) == 1 and result.tracks[4].notes == []
    assert [source.note_view for source in result.sources] == ["imported", "cleaned"]
    assert result.sources[1].midi.cleanup == cleaned.cleanup
    assert result.sources[1].midi.tracks[1].events == imported.tracks[1].events


def test_cleaned_extent_can_exceed_original_track_end(tmp_path):
    midi = make_input(tmp_path, start=60, duration=1, trailing=0)
    cleaned = DeterministicMidiProcessor().clean(
        midi, MidiPreferences(quantize=True, quantize_grid_ticks=120)
    )
    result = FaithfulArrangementEngine().arrange(
        [cleaned], MusicalMetadata(), "faithful", options=ArrangementOptions(note_view="active")
    )
    assert result.tracks[1].end_tick == 121
    assert result.sources[0].midi.tracks[1].end_tick == 61
    assert result.tracks[1].note_origins[0].input_start_tick == 120
    assert result.tracks[1].notes[0].original_start_tick == 60


@pytest.mark.parametrize("kind", ["tempo", "meter", "later_change", "implicit_default"])
def test_conflicting_effective_maps_reject_or_require_explicit_authority(tmp_path, kind):
    first = make_input(tmp_path, tempos=[(0, 500000)], meters=[(0, 4, 4)])
    settings = {"tempos": [(0, 600000)]} if kind == "tempo" else {"meters": [(0, 3, 4)]}
    if kind == "later_change":
        settings = {"tempos": [(0, 500000), (480, 600000)]}
    elif kind == "implicit_default":
        first = make_input(tmp_path, tempos=[(0, 600000)])
        settings = {}
    second = make_input(tmp_path, "two", **settings)
    engine = FaithfulArrangementEngine()
    with pytest.raises(TimingConflictError):
        engine.arrange([first, second], MusicalMetadata(), "faithful")
    result = engine.arrange(
        [first, second], MusicalMetadata(), "faithful", options=ArrangementOptions(timing_source=0)
    )
    assert any(d.code == "timing_conflict_overridden" for d in result.diagnostics)
    assert result.sources[1].midi == second
    assert result.tempo_map[0].source_input == 0


def test_redundant_timing_events_do_not_create_false_conflicts(tmp_path):
    first = make_input(tmp_path, tempos=[(0, 500000), (240, 500000), (480, 600000)])
    second = make_input(tmp_path, "two", tempos=[(480, 600000)])
    result = FaithfulArrangementEngine().arrange([first, second], MusicalMetadata(), "faithful")
    assert [(e.tick, e.microseconds_per_beat) for e in result.tempo_map] == [
        (0, 500000),
        (480, 600000),
    ]
    assert len(result.sources[0].midi.tempo_map) == 3


def test_internal_conflicts_and_rounding_map_collisions_are_not_silently_resolved(tmp_path):
    midi = make_input(tmp_path, tempos=[(0, 500000), (0, 600000)])
    with pytest.raises(TimingConflictError):
        FaithfulArrangementEngine().arrange(
            [midi], MusicalMetadata(), "faithful", options=ArrangementOptions(timing_source=0)
        )
    midi = make_input(tmp_path, tempos=[(1, 600000), (2, 700000)])
    with pytest.raises(ArrangementError, match="collid|PPQ|conflict"):
        FaithfulArrangementEngine().arrange(
            [midi],
            MusicalMetadata(),
            "faithful",
            options=ArrangementOptions(target_ppq=1, ppq_rounding="nearest"),
        )


def test_invalid_inputs_and_unsupported_modes_are_explicit(tmp_path):
    midi = make_input(tmp_path)
    engine = FaithfulArrangementEngine()
    with pytest.raises(ArrangementError):
        engine.arrange([], MusicalMetadata(), "faithful")
    with pytest.raises(ArrangementError):
        engine.arrange([midi], MusicalMetadata(), "reinterpretation")
    with pytest.raises(ArrangementError):
        engine.arrange(
            [midi], MusicalMetadata(), "faithful", options=ArrangementOptions(timing_source=1)
        )
    midi.diagnostics.append(Diagnostic(code="bad", severity="error", message="invalid input"))
    with pytest.raises(ArrangementError):
        engine.arrange([midi], MusicalMetadata(), "faithful")


@pytest.mark.parametrize(
    "settings",
    [
        {"target_ppq": 0},
        {"target_ppq": 1.5},
        {"target_ppq": True},
        {"ppq_rounding": "silent"},
        {"note_view": "guess"},
        {"timing_source": -1},
    ],
)
def test_invalid_arrangement_options(settings):
    with pytest.raises(ValidationError):
        ArrangementOptions(**settings)


def test_authority_can_select_later_input_and_ignore_other_internal_conflicts(tmp_path):
    first = make_input(tmp_path, tempos=[(0, 500000), (0, 600000)])
    second = make_input(tmp_path, "two", ppq=720, tempos=[(0, 700000), (720, 800000)])
    result = FaithfulArrangementEngine().arrange(
        [first, second], MusicalMetadata(), "faithful", options=ArrangementOptions(timing_source=1)
    )
    assert [(e.tick, e.microseconds_per_beat) for e in result.tempo_map] == [
        (0, 700000),
        (1440, 800000),
    ]
    assert all(e.source_input == 1 for e in result.tempo_map)
    assert any(
        d.code == "timing_conflict_overridden" and d.source_input == 0 for d in result.diagnostics
    )
    assert result.sources[0].midi.tempo_map == first.tempo_map


def test_exact_half_tick_rounding_is_later_and_zero_notes_are_retained(tmp_path):
    midi = make_input(tmp_path, ppq=2, start=1, duration=2, trailing=0)
    result = FaithfulArrangementEngine().arrange(
        [midi],
        MusicalMetadata(),
        "faithful",
        options=ArrangementOptions(target_ppq=1, ppq_rounding="nearest"),
    )
    assert (result.tracks[1].notes[0].start_tick, result.tracks[1].notes[0].duration_ticks) == (
        1,
        1,
    )
    zero = make_input(tmp_path, "zero", ppq=2, start=1, duration=0, trailing=0)
    result = FaithfulArrangementEngine().arrange(
        [zero],
        MusicalMetadata(),
        "faithful",
        options=ArrangementOptions(target_ppq=1, ppq_rounding="nearest"),
    )
    assert (result.tracks[1].notes[0].start_tick, result.tracks[1].notes[0].duration_ticks) == (
        1,
        0,
    )


def test_map_mismatch_is_detected_before_rounding_can_hide_it(tmp_path):
    first = make_input(tmp_path, tempos=[(120, 600000)], start=0, duration=480, trailing=0)
    second = make_input(tmp_path, "two", tempos=[(121, 600000)], start=0, duration=480, trailing=0)
    with pytest.raises(TimingConflictError):
        FaithfulArrangementEngine().arrange(
            [first, second],
            MusicalMetadata(),
            "faithful",
            options=ArrangementOptions(target_ppq=2, ppq_rounding="nearest"),
        )


def test_missing_provenance_or_unrecorded_note_edits_are_rejected(tmp_path):
    midi = make_input(tmp_path)
    midi.tracks[1].notes[0].original_start_tick = None
    with pytest.raises(ArrangementError, match="original"):
        FaithfulArrangementEngine().arrange([midi], MusicalMetadata(), "faithful")
    midi = make_input(tmp_path)
    midi.tracks[1].notes[0].start_tick += 1
    with pytest.raises(ArrangementError, match="provenance|edits"):
        FaithfulArrangementEngine().arrange([midi], MusicalMetadata(), "faithful")


def test_unknown_hash_is_reported_and_not_invented(tmp_path):
    midi = make_input(tmp_path)
    midi.source_sha256 = None
    result = FaithfulArrangementEngine().arrange([midi], MusicalMetadata(), "faithful")
    assert result.sources[0].midi.source_sha256 is None
    assert any(d.code == "source_hash_unverified" for d in result.diagnostics)
