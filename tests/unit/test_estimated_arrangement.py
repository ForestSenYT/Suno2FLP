"""Original estimated evidence; exact clock oracles never invoke a model/DAW."""

from fractions import Fraction
from pathlib import Path

import pytest

from suno2flp.arrangement.inferred import build_estimated_arrangement
from suno2flp.core.beat_clock import beat_anchor
from suno2flp.core.estimated_arrangement import EstimatedArrangementInputs
from suno2flp.core.note_scoring import time_fraction


def identity(name):
    return dict(path=str(Path(name).absolute()), sha256="a" * 64, size_bytes=0, mtime_ns=0)


def inputs(*, frames=120000, rate=44100, notes=None):
    notes = (
        notes
        if notes is not None
        else [
            dict(start_frame=141, end_frame=143, pitch=60, activation=0.7, bend_offset=0),
            dict(start_frame=141, end_frame=142, pitch=64, activation=0.4, bend_offset=2),
        ]
    )
    bends = {
        **identity("bends"),
        "size_bytes": sum(n["end_frame"] - n["start_frame"] for n in notes),
    }
    return EstimatedArrangementInputs.model_validate(
        dict(
            source_audio=identity("source.wav"),
            decode_report=identity("decode.json"),
            pcm=identity("decoded.wav"),
            frames=frames,
            sample_rate=rate,
            channels=1,
            batch_report=identity("stem-transcription.json"),
            separation_report=identity("separation.json"),
            stems=[
                dict(stem=s, file=identity(s + ".wav"))
                for s in ("vocals", "drums", "bass", "other")
            ],
            residual=identity("residual.wav"),
            pitches=[
                dict(
                    stem=s,
                    transcription=identity(s + "/transcription.json"),
                    source_audio=identity("source.wav"),
                    decode_report=identity("decode.json"),
                    estimated_audio=identity(s + ".wav"),
                    frames=frames,
                    sample_rate=rate,
                    notes=notes,
                    bends=bends,
                )
                for s in ("vocals", "bass", "other")
            ],
        )
    )


def test_seam_order_overlaps_bends_roles_and_reference_are_retained():
    source = inputs()
    result = build_estimated_arrangement(source)
    assert result.inputs == source and result.inputs is not source
    assert [p.stem for p in result.parts] == ["vocals", "drums", "bass", "other"]
    assert [p.role for p in result.parts] == [
        "vocal-pitch-proxy",
        "percussion-reference",
        "bass",
        "mixed-pitched",
    ]
    first, overlap = result.parts[0].notes
    assert [n.source_note_index for n in result.parts[0].notes] == [0, 1]
    assert time_fraction(first.start.source_sample) == 72192
    assert time_fraction(first.end.source_sample) == 72840
    assert time_fraction(overlap.end.source_sample) == 72328
    assert time_fraction(first.start.microseconds) == Fraction(36096 * 1000000, 22050)
    assert all(
        p.reference.muted and time_fraction(p.reference.end_sample) == 120000 for p in result.parts
    )
    assert result.residual.file == source.residual and result.residual.muted
    assert result.parts[1].notes == []
    assert result.inputs.pitches[0].bends.size_bytes == 3
    assert result.inputs.pitches[0].notes[1].bend_offset == 2
    assert result.writer_eligibility == "blocked" and result.execution_allowed is False
    assert "drums-not-transcribed" in result.blockers
    source.pitches[0].notes.clear()
    assert len(result.inputs.pitches[0].notes) == 2


def test_final_end_uses_full_extent_without_clamping_fractional_padding():
    source = inputs(
        frames=37,
        rate=48000,
        notes=[dict(start_frame=0, end_frame=1, pitch=60, activation=0.5, bend_offset=0)],
    )
    end = build_estimated_arrangement(source).parts[0].notes[0].end
    assert end.row_boundary == 1 and end.resampled_sample == 17
    assert time_fraction(end.source_sample) == Fraction(17 * 48000, 22050)
    assert time_fraction(end.source_sample) > 37 and end.domain == "padding"


@pytest.mark.parametrize(
    "field,value",
    [
        ("frames", 119999),
        ("sample_rate", 48000),
        ("source_audio", identity("other.wav")),
        ("decode_report", identity("other.json")),
        ("estimated_audio", identity("drums.wav")),
    ],
)
def test_mismatched_song_clock_or_stem_is_refused(field, value):
    source = inputs()
    setattr(source.pitches[0], field, value)
    with pytest.raises(ValueError):
        build_estimated_arrangement(source)


def test_partial_mutated_or_unaddressed_bends_are_refused():
    source = inputs()
    source.pitches.pop()
    with pytest.raises(ValueError):
        build_estimated_arrangement(source)
    source = inputs()
    source.pitches[0].notes[1].bend_offset = 0
    with pytest.raises(ValueError):
        build_estimated_arrangement(source)
    source = inputs()
    source.pitches[0].notes[0].end_frame = 900
    with pytest.raises(ValueError):
        build_estimated_arrangement(source)


def test_empty_estimates_are_explicit_and_no_tempo_meter_or_synth_is_invented():
    result = build_estimated_arrangement(inputs(notes=[]))
    assert "empty-pitched-estimates" in result.blockers
    assert result.tempo == result.meter == result.structure == "unavailable"
    assert result.playback == "unavailable" and result.model_qualification == "not_assessed"
    assert result.ground_truth_metrics == "unavailable"
    assert result.role_basis == "estimated-separation-stem-labels"


def with_rhythm():
    source = inputs()
    anchor = beat_anchor(Fraction(25), sample_rate=44100, source_frames=120000)
    raw = beat_anchor(Fraction(51, 2), sample_rate=44100, source_frames=120000)
    return EstimatedArrangementInputs.model_validate(
        {
            **source.model_dump(),
            "rhythm": dict(
                report=identity("beats.json"),
                source_audio=source.source_audio,
                decode_report=source.decode_report,
                pcm=source.pcm,
                frames=source.frames,
                sample_rate=source.sample_rate,
                channels=1,
                beats=[anchor],
                raw_downbeats=[raw],
                downbeat_to_beat=[0],
                downbeats=[anchor],
                signal_observations=[],
            ),
        }
    )


def test_rhythm_preserves_raw_half_frames_and_alignment_without_inventing_meter():
    source = with_rhythm()
    result = build_estimated_arrangement(source)
    assert result.inputs.rhythm == source.rhythm
    assert time_fraction(result.inputs.rhythm.raw_downbeats[0].source_sample) == 22491
    assert result.inputs.rhythm.downbeat_to_beat == [0]
    assert "rhythm-not-provided" not in result.blockers
    assert result.tempo == result.meter == "unavailable"


@pytest.mark.parametrize("change", ["source", "clock", "anchor", "mapping", "aligned", "order"])
def test_rhythm_mismatch_or_mutation_is_refused(change):
    source = with_rhythm()
    rhythm = source.rhythm
    if change == "source":
        rhythm.source_audio.path = Path("another.wav").absolute()
    elif change == "clock":
        rhythm.frames -= 1
    elif change == "anchor":
        rhythm.beats[0].source_sample.numerator += 1
    elif change == "mapping":
        rhythm.downbeat_to_beat[:] = [2]
    elif change == "aligned":
        rhythm.downbeats.clear()
    else:
        rhythm.beats.append(rhythm.beats[0])
    with pytest.raises(ValueError):
        build_estimated_arrangement(source)


def test_boolean_mapping_is_not_an_integer_source_address():
    source = with_rhythm()
    source.rhythm.downbeat_to_beat[:] = [False]
    with pytest.raises(ValueError):
        build_estimated_arrangement(source)
