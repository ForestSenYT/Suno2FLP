import hashlib
import json
import struct
from pathlib import Path

import mido
import pytest
from mido.midifiles.meta import UnknownMetaMessage

from suno2flp.core.errors import MidiImportError
from suno2flp.core.models import ProcessedMidi
from suno2flp.importer import MidiFileImporter


def save_midi(tmp_path, tracks, *, format=1, ppq=960):
    midi = mido.MidiFile(type=format, ticks_per_beat=ppq)
    midi.tracks.extend(mido.MidiTrack(events) for events in tracks)
    source = tmp_path / "source.mid"
    midi.save(source)
    return source


def test_multitrack_import_preserves_ticks_maps_events_and_source(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [
                mido.MetaMessage("track_name", name="Conductor"),
                mido.MetaMessage("set_tempo", tempo=500000),
                mido.MetaMessage("time_signature", numerator=4, denominator=4),
                mido.MetaMessage("set_tempo", tempo=600000, time=1920),
                mido.MetaMessage("time_signature", numerator=7, denominator=8, time=960),
                mido.MetaMessage("end_of_track", time=1920),
            ],
            [
                mido.MetaMessage("track_name", name="Piano"),
                mido.Message("program_change", channel=2, program=10),
                mido.Message("note_on", channel=2, note=60, velocity=91, time=119),
                mido.Message("control_change", channel=2, control=64, value=127, time=1),
                mido.Message("note_off", channel=2, note=60, velocity=29, time=481),
                mido.Message("sysex", data=[1, 2, 3], time=7),
                mido.MetaMessage("end_of_track", time=100),
            ],
            [mido.MetaMessage("end_of_track", time=42)],
        ],
    )
    before = source.read_bytes()
    result = MidiFileImporter().import_file(source)
    assert result.format == 1 and result.ticks_per_beat == 960
    assert [t.name for t in result.tracks] == ["Conductor", "Piano", "Track 3"]
    assert [t.index for t in result.tracks] == [0, 1, 2]
    assert [t.end_tick for t in result.tracks] == [4800, 708, 42]
    assert [(e.tick, e.microseconds_per_beat) for e in result.tempo_map] == [
        (0, 500000),
        (1920, 600000),
    ]
    assert [(e.tick, e.numerator, e.denominator) for e in result.meter_map] == [
        (0, 4, 4),
        (2880, 7, 8),
    ]
    assert result.tempo_map[1].source_track == 0
    assert result.tempo_map[1].source_event == 3
    note = result.tracks[1].notes[0]
    assert (note.pitch, note.channel, note.velocity) == (60, 2, 91)
    assert note.start_tick == note.original_start_tick == 119
    assert note.duration_ticks == note.original_duration_ticks == 482
    events = result.tracks[1].events
    assert [e.delta_ticks for e in events] == [0, 0, 119, 1, 481, 7, 100]
    assert [e.tick for e in events] == [0, 0, 119, 120, 601, 608, 708]
    assert events[4].message["velocity"] == 29
    assert events[5].message["data"] == [1, 2, 3]
    assert note.note_on_event_index == 2 and note.note_off_event_index == 4
    decoded = mido.MidiFile(source)
    for track, original in zip(result.tracks, decoded.tracks, strict=True):
        assert [event.message for event in track.events] == [
            json.loads(json.dumps(message.dict())) for message in original
        ]
    assert not result.diagnostics
    assert result.source_sha256 == hashlib.sha256(before).hexdigest()
    assert result.source == source.resolve()
    assert source.read_bytes() == before
    assert ProcessedMidi.model_validate_json(result.model_dump_json()) == result
    assert MidiFileImporter().import_file(source) == result


def test_format_zero_channels_velocity_zero_and_same_tick_order(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", channel=0, note=60, velocity=70, time=10),
                mido.Message("note_on", channel=1, note=60, velocity=90, time=5),
                mido.Message("note_on", channel=0, note=60, velocity=0, time=5),
                mido.Message("note_off", channel=1, note=60, time=0),
                mido.Message("note_on", channel=0, note=62, velocity=50),
                mido.Message("note_off", channel=0, note=62),
            ]
        ],
        format=0,
    )
    result = MidiFileImporter().import_file(source)
    assert result.format == 0
    assert [(n.channel, n.start_tick, n.duration_ticks) for n in result.tracks[0].notes] == [
        (0, 10, 10),
        (1, 15, 5),
        (0, 20, 0),
    ]
    assert not result.tempo_map and not result.meter_map  # No invented source events.
    assert not result.diagnostics


def test_notes_do_not_pair_across_tracks(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [mido.Message("note_on", note=60, time=10)],
            [mido.Message("note_off", note=60, time=20)],
        ],
    )
    result = MidiFileImporter().import_file(source)
    assert not any(track.notes for track in result.tracks)
    assert {d.code for d in result.diagnostics} == {"unclosed_note", "unmatched_note_off"}
    assert all(d.severity == "warning" for d in result.diagnostics)
    assert result.tracks[0].events[0].tick == 10


def test_overlapping_same_pitch_uses_fifo_with_warning(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [
                mido.Message("note_on", note=60, velocity=70),
                mido.Message("note_on", note=60, velocity=80, time=10),
                mido.Message("note_off", note=60, time=10),
                mido.Message("note_off", note=60, time=10),
            ]
        ],
    )
    result = MidiFileImporter().import_file(source)
    assert [(n.start_tick, n.duration_ticks, n.velocity) for n in result.tracks[0].notes] == [
        (0, 20, 70),
        (10, 20, 80),
    ]
    assert [d.code for d in result.diagnostics] == ["overlapping_note"]


def test_global_maps_sort_by_tick_track_event_without_discarding_conflicts(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [
                mido.MetaMessage("set_tempo", tempo=500000, time=20),
                mido.MetaMessage("time_signature", numerator=3, denominator=4),
            ],
            [
                mido.MetaMessage("set_tempo", tempo=400000, time=10),
                mido.MetaMessage("set_tempo", tempo=600000, time=10),
                mido.MetaMessage("time_signature", numerator=6, denominator=8),
            ],
        ],
    )
    result = MidiFileImporter().import_file(source)
    assert [(e.tick, e.source_track) for e in result.tempo_map] == [(10, 1), (20, 0), (20, 1)]
    assert [(e.tick, e.source_track) for e in result.meter_map] == [(20, 0), (20, 1)]
    assert {d.code for d in result.diagnostics} == {"conflicting_tempo", "conflicting_meter"}


def test_extended_meter_fields_and_denominator_are_preserved(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [
                mido.MetaMessage(
                    "time_signature",
                    numerator=5,
                    denominator=128,
                    clocks_per_click=36,
                    notated_32nd_notes_per_beat=12,
                    time=7,
                )
            ]
        ],
    )
    meter = MidiFileImporter().import_file(source).meter_map[0]
    assert (
        meter.tick,
        meter.denominator,
        meter.clocks_per_click,
        meter.notated_32nd_notes_per_beat,
    ) == (7, 128, 36, 12)


def test_invalid_tempo_and_meter_are_retained_raw_and_diagnosed(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [[mido.MetaMessage("set_tempo", tempo=0), mido.MetaMessage("time_signature", numerator=0)]],
    )
    result = MidiFileImporter().import_file(source)
    assert not result.tempo_map and not result.meter_map
    assert {d.code for d in result.diagnostics} == {"invalid_tempo", "invalid_meter"}
    assert all(d.severity == "error" for d in result.diagnostics)
    assert len(result.tracks[0].events) == 3


@pytest.mark.parametrize(
    "data", [b"", b"not midi", b"MThd", b"MThd" + struct.pack(">IHHH", 6, 1, 1, 480)]
)
def test_unreadable_or_malformed_source_raises_typed_error(tmp_path: Path, data: bytes):
    source = tmp_path / "broken.mid"
    source.write_bytes(data)
    with pytest.raises(MidiImportError):
        MidiFileImporter().import_file(source)
    with pytest.raises(MidiImportError):
        MidiFileImporter().import_file(tmp_path / "missing.mid")


@pytest.mark.parametrize("format,ppq", [(2, 480), (1, -6360), (1, 0)])
def test_unsupported_timing_is_explicit(tmp_path: Path, format: int, ppq: int):
    source = save_midi(tmp_path, [[mido.MetaMessage("end_of_track")]], format=format, ppq=ppq)
    with pytest.raises(MidiImportError, match="Type 2|PPQ|SMPTE"):
        MidiFileImporter().import_file(source)


def test_running_status_unknown_meta_and_release_order_are_preserved(tmp_path: Path):
    # Running-status note-on, unknown meta event, two releases in reverse pitch order.
    events = bytes.fromhex("00903c40073e4100ff70030102030b803e000d3c0000ff2f00")
    source = tmp_path / "running.mid"
    source.write_bytes(
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, 480)
        + b"MTrk"
        + struct.pack(">I", len(events))
        + events
    )
    result = MidiFileImporter().import_file(source)
    track = result.tracks[0]
    assert [(n.pitch, n.start_tick, n.duration_ticks) for n in track.notes] == [
        (60, 0, 31),
        (62, 7, 11),
    ]
    assert track.events[2].message["type"] == "unknown_meta"
    assert track.events[2].message["data"] == [1, 2, 3]
    assert track.end_tick == 31


def test_identical_map_events_are_retained_without_conflict(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [
                mido.MetaMessage("set_tempo", tempo=500000),
                mido.MetaMessage("time_signature", numerator=4),
            ]
            for _ in range(2)
        ],
    )
    result = MidiFileImporter().import_file(source)
    assert len(result.tempo_map) == len(result.meter_map) == 2
    assert not result.diagnostics


def test_unknown_meta_nonzero_delta_does_not_shift_notes_or_maps(tmp_path: Path):
    # Unknown meta at tick 130 (multi-byte delta); later release/tempo/meter at tick 150.
    events = bytes.fromhex("00903c408102ff700301020314803c0000ff510307a12000ff58040402180800ff2f00")
    source = tmp_path / "unknown-timed.mid"
    source.write_bytes(
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, 480)
        + b"MTrk"
        + struct.pack(">I", len(events))
        + events
    )
    result = MidiFileImporter().import_file(source)
    track = result.tracks[0]
    assert track.notes[0].duration_ticks == track.notes[0].original_duration_ticks == 150
    assert track.events[1].delta_ticks == track.events[1].message["time"] == 130
    assert track.events[1].tick == 130
    assert result.tempo_map[0].tick == result.meter_map[0].tick == track.end_tick == 150


def test_invalid_key_signature_raises_domain_error(tmp_path: Path):
    events = bytes.fromhex("00ff5902080000ff2f00")
    source = tmp_path / "invalid-key.mid"
    source.write_bytes(
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, 480)
        + b"MTrk"
        + struct.pack(">I", len(events))
        + events
    )
    with pytest.raises(MidiImportError):
        MidiFileImporter().import_file(source)


def test_unknown_meta_timing_check_handles_multiple_tracks_sysex_and_short_messages(tmp_path: Path):
    source = save_midi(
        tmp_path,
        [
            [mido.MetaMessage("set_tempo", tempo=500000)],
            [
                mido.Message("program_change", program=10, time=3),
                mido.Message("aftertouch", value=40, time=2),
                mido.Message("sysex", data=[1] * 129, time=5),
                UnknownMetaMessage(0x70, data=[1] * 130, time=16384),
                mido.Message("note_on", note=60, time=7),
                UnknownMetaMessage(0x71, data=[2], time=11),
                mido.Message("note_off", note=60, time=13),
            ],
        ],
    )
    result = MidiFileImporter().import_file(source)
    track = result.tracks[1]
    assert track.notes[0].start_tick == 16401
    assert track.notes[0].duration_ticks == 24
    assert track.end_tick == 16425
    assert [event.delta_ticks for event in track.events] == [3, 2, 5, 16384, 7, 11, 13, 0]
    assert len(track.events[2].message["data"]) == 129
