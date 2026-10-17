"""Authored metadata and independent rational clocks; no native/DAW calls."""

from fractions import Fraction

import pytest
from test_estimated_arrangement import identity
from test_estimated_arrangement import inputs as pitched_inputs

from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.drum_peaks import DrumPeak, RejectedDrumPeak
from suno2flp.core.drum_scoring import DRUM_CLASSES, ScoredDrum
from suno2flp.core.note_scoring import time_fraction
from suno2flp.core.percussion_arrangement import (
    EstimatedDrumInput,
    PercussionArrangementInputs,
)
from suno2flp.core.performance import RationalTime
from suno2flp.core.transcription_clock import owned_prediction_rows


def inputs():
    base = pitched_inputs(
        frames=2000,
        rate=48000,
        notes=[dict(start_frame=0, end_frame=1, pitch=60, activation=0.7, bend_offset=0)],
    )
    peaks = [
        DrumPeak(
            id=f"{label}.{row}",
            label=label,
            row=row,
            model_sample=(row - 6) * 256,
            domain=domain,
            logit_bits=0x40000000,
            velocity_bits=0x3F000000,
        )
        for label, row, domain in [
            ("CY_RD", 13, "source"),
            ("SD", 0, "leading_padding"),
            ("KD", 7, "source"),
            ("HH_CHH", 14, "tail_padding"),
        ]
    ]
    replay = identity("sep-replay/replay.json")
    report = identity("drum-producer/drum-transcription.json")
    native = [
        identity("drum-producer/native/" + name)
        for name in (
            "request.json",
            "result.json",
            "mono.f32",
            "onsets.f32",
            "velocities.f32",
            "stdout.bin",
            "stderr.bin",
        )
    ]
    drums = EstimatedDrumInput(
        transcription=report,
        backend_record=identity("drum-backend/backend.json"),
        native_witnesses=native,
        source_audio=base.source_audio,
        decode_report=base.decode_report,
        pcm=base.pcm,
        separation_report=base.separation_report,
        separation_replay=replay,
        reference=base.stems[1].file,
        model_pcm={**identity("drums-model.f32"), "size_bytes": 1838 * 8},
        frames=2000,
        sample_rate=48000,
        channels=1,
        model_frames=1838,
        rows=21,
        peaks=peaks,
        events=[
            ScoredDrum(
                id=p.id,
                label=p.label,
                microseconds=RationalTime.exact(Fraction(p.model_sample * 1000000, 44100)),
            )
            for p in peaks
            if p.domain == "source"
        ],
        rejected_peaks=[
            RejectedDrumPeak(peak=p, reason=reason)
            for p, reason in [
                (peaks[1], "before-source-zero"),
                (peaks[3], "at-or-after-original-end"),
            ]
        ],
    )
    return PercussionArrangementInputs(pitched=base, pitched_separation_replay=replay, drums=drums)


def test_exact_two_clocks_source_order_padding_bits_and_detached_inputs():
    source = inputs()
    frozen = source.model_dump_json()
    record = build_percussion_arrangement(source)
    assert record.profile == "source-clock-estimated-arrangement-v2"
    assert [p.stem for p in record.parts] == ["vocals", "drums", "bass", "other"]
    assert record.parts[0].notes and record.parts[1].notes == []
    onsets = record.parts[1].onsets
    assert [p.source_event_index for p in onsets] == [0, 1]
    assert [p.source_peak_index for p in onsets] == [0, 2]
    assert [time_fraction(p.source_sample) for p in onsets] == [
        Fraction(1792 * 48000, 44100),
        Fraction(256 * 48000, 44100),
    ]
    assert time_fraction(onsets[1].microseconds) == Fraction(2560000, 441)
    assert record.inputs.drums.peaks == source.drums.peaks
    assert record.inputs.drums.rejected_peaks == source.drums.rejected_peaks
    assert source.model_dump_json() == frozen
    source.drums.peaks.clear()
    source.pitched.pitches[0].notes.clear()
    assert len(record.inputs.drums.peaks) == 4 and record.inputs.pitched.pitches[0].notes
    assert record.execution_allowed is False and record.writer_eligibility == "blocked"
    assert record.tempo == record.meter == record.structure == record.playback == "unavailable"
    assert "drums-not-transcribed" not in record.blockers
    assert "drum-latency-not-calibrated" in record.blockers
    assert "drum-gm-routing-unavailable" in record.blockers
    assert {"duration", "velocity"}.isdisjoint(onsets[0].model_dump())


@pytest.mark.parametrize(
    "field",
    ["source_audio", "decode_report", "pcm", "separation_report", "separation_replay", "reference"],
)
def test_foreign_identity_cannot_be_joined_by_equal_duration(field):
    source = inputs()
    setattr(source.drums, field, type(source.drums.reference).model_validate(identity("foreign")))
    with pytest.raises(ValueError):
        build_percussion_arrangement(source)


@pytest.mark.parametrize("field,value", [("frames", 2001), ("sample_rate", 44100), ("channels", 2)])
def test_foreign_original_clock_is_rejected(field, value):
    source = inputs()
    with pytest.raises(ValueError):
        setattr(source.drums, field, value)
        build_percussion_arrangement(source)


@pytest.mark.parametrize(
    "change", ["rows", "model_frames", "event", "order", "missing", "duplicate", "rejection"]
)
def test_incomplete_or_changed_peak_geometry_mapping_fails(change):
    source = inputs()
    drum = source.drums
    with pytest.raises(ValueError):
        if change == "rows":
            drum.rows += 1
        elif change == "model_frames":
            drum.model_frames -= 1
        elif change == "event":
            drum.events[0].microseconds = RationalTime.exact(Fraction(1))
        elif change == "order":
            drum.events.reverse()
        elif change == "missing":
            drum.events.pop()
        elif change == "duplicate":
            drum.peaks.append(drum.peaks[0].model_copy(deep=True))
        else:
            drum.rejected_peaks.pop()
        build_percussion_arrangement(source)


def test_all_nine_labels_are_retained_without_gm_or_velocity_invention():
    source = inputs()
    seed = source.drums.peaks[2]
    peaks = [seed.model_copy(update=dict(id=f"{label}.7", label=label)) for label in DRUM_CLASSES]
    events = [
        ScoredDrum(id=p.id, label=p.label, microseconds=source.drums.events[1].microseconds)
        for p in peaks
    ]
    source.drums = EstimatedDrumInput.model_validate(
        {**source.drums.model_dump(), "peaks": peaks, "events": events, "rejected_peaks": []}
    )
    record = build_percussion_arrangement(source)
    assert [e.label for e in record.inputs.drums.events] == list(DRUM_CLASSES)
    assert len(record.parts[1].onsets) == 9
    assert all(p.logit_bits == 0x40000000 for p in record.inputs.drums.peaks)
    assert record.parts[1].role == "classified-percussion-candidate"


def test_empty_estimates_remain_explicitly_unqualified():
    source = inputs()
    source.drums = EstimatedDrumInput.model_validate(
        {**source.drums.model_dump(), "peaks": [], "events": [], "rejected_peaks": []}
    )
    record = build_percussion_arrangement(source)
    assert record.parts[1].onsets == []
    assert "empty-drum-estimates" in record.blockers
    assert record.model_qualification == "not_assessed"


def test_pitched_final_padding_is_not_clamped_to_drum_or_original_end():
    source = inputs()
    end = len(owned_prediction_rows(919))
    source.pitched = pitched_inputs(
        frames=2000,
        rate=48000,
        notes=[dict(start_frame=0, end_frame=end, pitch=60, activation=0.7, bend_offset=0)],
    )
    record = build_percussion_arrangement(source)
    boundary = record.parts[0].notes[0].end
    assert time_fraction(boundary.source_sample) == Fraction(919 * 48000, 22050)
    assert boundary.domain == "padding" and time_fraction(boundary.source_sample) > 2000
    assert record.inputs.drums.rejected_peaks == source.drums.rejected_peaks
    assert len(record.parts[1].onsets) == 2
