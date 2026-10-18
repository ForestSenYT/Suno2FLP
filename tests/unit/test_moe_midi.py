"""Original tiny inferred-note fixtures: no model, backend, real song or DAW."""

import struct
from copy import deepcopy
from fractions import Fraction
from io import BytesIO
from pathlib import Path

import mido
import pytest

from suno2flp.arrangement.moe_midi import encode_moe_part, project_moe_midi
from suno2flp.core.moe_midi import MoEMidiChannel, MoEMidiInputs
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.yourmt3 import FrameInterval, YourMT3Note
from suno2flp.core.yourmt3_moe import YourMT3MoECandidate
from suno2flp.integrations.yourmt3_source import load_yourmt3_moe_pins
from suno2flp.validator.moe_midi import verify_moe_part


def native_note(**changes: object) -> YourMT3Note:
    data = dict(is_drum=False, program=0, pitch=60, onset=0.125, offset=0.25, velocity=1)
    data.update(changes)
    return YourMT3Note.model_validate(data)


@pytest.fixture
def inputs(tmp_path: Path) -> MoEMidiInputs:
    def identity(name: str):  # type: ignore[no-untyped-def]
        path = tmp_path / name
        path.write_bytes(b"original fixture provenance; not a native producer")
        return capture_stream_input(path)

    candidate = YourMT3MoECandidate(
        root=tmp_path,
        backend=identity("backend.json"),
        decode_report=identity("decode.json"),
        source_audio=identity("source.wav"),
        pcm=identity("decoded.wav"),
        frames=16000,
        sample_rate=16000,
        channels=1,
        intervals=[FrameInterval(start_frame=0, end_frame=16000)],
        raw=identity("native.json"),
        request=identity("request.json"),
        diagnostics=[identity("stdout.txt"), identity("stderr.txt")],
        summaries=[],
        unresolved_generations=[],
    )
    return MoEMidiInputs(
        producer=identity("yourmt3-moe.json"),
        candidate=candidate,
        model_channels=[
            MoEMidiChannel(channel=i, notes=[], decode_errors={}, merge_errors={})
            for i in range(13)
        ],
        program_channels=deepcopy(load_yourmt3_moe_pins().program_channels),
    )


def test_all_addresses_and_empty_source_are_retained(inputs: MoEMidiInputs) -> None:
    score = project_moe_midi(inputs)
    assert score.parts == []
    assert [c.channel for c in score.inputs.model_channels] == list(range(13))
    assert score.end_tick == 1920
    assert score.authority == "audio-inference"
    assert score.writer_eligibility == "blocked" and not score.execution_allowed
    inputs.model_channels[0].notes.append(native_note())
    assert score.inputs.model_channels[0].notes == []


def test_original_order_half_tick_and_bits_are_preserved(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[0].notes = [
        native_note(onset=0.25, offset=0.5),
        native_note(onset=1 / 256, offset=3 / 256, pitch=61),
        native_note(onset=-0.0, offset=0.125, pitch=62),
    ]
    before = inputs.model_dump_json()
    score = project_moe_midi(inputs)
    assert inputs.model_dump_json() == before
    a, b, zero = score.parts[0].notes
    assert [a.source_index, b.source_index, zero.source_index] == [0, 1, 2]
    assert (b.start.tick, b.end.tick) == (8, 23)
    assert b.start.error_us.numerator == 3125 and b.start.error_us.denominator == 12
    assert b.onset_bits == struct.pack("<d", 1 / 256).hex()
    assert zero.onset_bits == "0000000000000080"
    assert b.native.velocity == 1
    assert score.inputs.model_channels[0].notes[2].onset.hex() == (-0.0).hex()
    inputs.model_channels[0].notes[0].pitch = 70
    assert a.native.pitch == 60


def test_separate_programs_are_never_collapsed_to_primary_hint(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[0].notes = [native_note(program=2), native_note()]
    score = project_moe_midi(inputs)
    assert [(p.source_channel, p.model_program) for p in score.parts] == [(0, 0), (0, 2)]
    assert score.parts[0].notes[0].source_index == 1
    assert score.parts[1].notes[0].source_index == 0


def test_model_voice100_is_metadata_and_no_gm_message(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[11].notes = [native_note(program=100)]
    score = project_moe_midi(inputs)
    part = score.parts[0]
    assert (part.source_channel, part.model_program, part.midi_channel) == (11, 100, 0)
    assert part.instrument_group_hint == "Singing Voice"
    raw = encode_moe_part(part, score.end_tick)
    verify_moe_part(raw, part, score.end_tick)
    midi = mido.MidiFile(file=BytesIO(raw))
    assert midi.type == 1 and midi.ticks_per_beat == 960 and len(midi.tracks) == 2
    assert {m.type for track in midi.tracks for m in track} == {
        "track_name",
        "set_tempo",
        "end_of_track",
        "note_on",
        "note_off",
    }
    assert all(m.channel == 0 for track in midi.tracks for m in track if not m.is_meta)
    assert next(m for track in midi.tracks for m in track if m.type == "note_on").velocity == 96


def test_drum_address_and_original_inferred_duration(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[12].notes = [native_note(program=128, is_drum=True, pitch=38)]
    score = project_moe_midi(inputs)
    part = score.parts[0]
    assert part.midi_channel == 9
    assert (part.notes[0].start.tick, part.notes[0].end.tick) == (240, 480)
    assert part.notes[0].native.velocity == 1


@pytest.mark.parametrize(
    "notes",
    [
        [dict(offset=1.01)],
        [dict(onset=0.0, offset=1e-8)],
        [dict(onset=0.0, offset=0.9), dict(onset=0.1, offset=0.8)],
        [dict(program=100)],
    ],
)
def test_unrepresentable_source_is_refused(inputs: MoEMidiInputs, notes: list[dict]) -> None:
    inputs.model_channels[0].notes = [native_note(**n) for n in notes]
    with pytest.raises(ValueError):
        project_moe_midi(inputs)


def test_incomplete_generation_is_not_exported(inputs: MoEMidiInputs) -> None:
    inputs.candidate.unresolved_generations = [(0, 0)]
    with pytest.raises(ValueError):
        project_moe_midi(inputs)


def test_resource_limit_never_truncates(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[0].notes = [native_note()] * 20001
    with pytest.raises(ValueError):
        project_moe_midi(inputs)
    assert len(inputs.model_channels[0].notes) == 20001


def test_native_errors_stay_in_owned_source_snapshot(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[0].decode_errors = {"fixture-decode-error": 2}
    inputs.model_channels[0].merge_errors = {"fixture-merge-error": 1}
    score = project_moe_midi(inputs)
    assert score.inputs.model_channels[0].decode_errors == {"fixture-decode-error": 2}
    assert score.inputs.model_channels[0].merge_errors == {"fixture-merge-error": 1}
    assert score.writer_eligibility == "blocked"


@pytest.mark.parametrize("mutation", ["tail", "header", "delta", "data", "label"])
def test_complete_smf_corruption_is_rejected(inputs: MoEMidiInputs, mutation: str) -> None:
    inputs.model_channels[0].notes = [native_note()]
    score = project_moe_midi(inputs)
    part = score.parts[0]
    raw = bytearray(encode_moe_part(part, score.end_tick))
    if mutation == "tail":
        raw.extend(b"!")
    elif mutation == "header":
        raw[13] = 1
    elif mutation == "delta":
        size = int.from_bytes(raw[18:22], "big")
        raw[18:22] = (size + 1).to_bytes(4, "big")
        raw[22:23] = b"\x80\x00"
    elif mutation == "data":
        raw[raw.index(b"\x90\x3c\x60") + 1] = 0xFF
    else:
        raw = raw.replace(b"Unqualified", b"Xnqualified")
    with pytest.raises(ValueError):
        verify_moe_part(bytes(raw), part, score.end_tick)


def test_all_boundary_errors_have_exact_original_units(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[0].notes = [native_note(onset=0.10000000000000002)]
    score = project_moe_midi(inputs)
    point = score.parts[0].notes[0].start
    original = Fraction.from_float(0.10000000000000002) * 1000000
    assert Fraction(point.original_us.numerator, point.original_us.denominator) == original
    assert Fraction(point.error_us.numerator, point.error_us.denominator) == (
        Fraction(point.tick * 500000, 960) - original
    )


@pytest.mark.parametrize("address", [True, -1, 13, 0.0])
def test_invalid_model_address_is_rejected(address: object) -> None:
    with pytest.raises(ValueError):
        MoEMidiChannel.model_validate(
            dict(channel=address, notes=[], decode_errors={}, merge_errors={})
        )


def test_negative_zero_and_source_index_tampering_fail(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[0].notes = [native_note(onset=-0.0)]
    score = project_moe_midi(inputs)
    part = score.parts[0]
    data = part.model_dump()
    data["notes"][0]["native"]["onset"] = 0.0
    with pytest.raises(ValueError):
        type(part).model_validate(data)


def test_positive_overlapping_fifo_occurrences_are_complete(inputs: MoEMidiInputs) -> None:
    inputs.model_channels[0].notes = [
        native_note(onset=0.0, offset=0.25),
        native_note(onset=0.125, offset=0.5),
        native_note(onset=0.25, offset=0.75),
    ]
    score = project_moe_midi(inputs)
    verify_moe_part(encode_moe_part(score.parts[0], score.end_tick), score.parts[0], score.end_tick)
