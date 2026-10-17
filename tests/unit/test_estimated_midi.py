"""Independent audio-clock/SMF oracles; no model, DAW or source MIDI edits."""

from fractions import Fraction
from io import BytesIO

import mido
import pytest
from test_estimated_arrangement import inputs as pitched_inputs
from test_percussion_arrangement import inputs

from suno2flp.arrangement.midi_preview import encode_estimated_midi, project_estimated_midi
from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.drum_clock import drum_output_rows
from suno2flp.core.drum_scoring import DRUM_CLASSES, ScoredDrum
from suno2flp.core.note_scoring import time_fraction
from suno2flp.core.percussion_arrangement import EstimatedDrumInput
from suno2flp.core.separation_clock import model_frame_count
from suno2flp.validator.midi_preview import verify_estimated_midi


def test_complete_occurrences_exact_signed_timing_and_technical_clock():
    original = build_percussion_arrangement(inputs())
    frozen = original.model_dump_json()
    score = project_estimated_midi(original)
    assert original.model_dump_json() == frozen
    assert score.arrangement == original and score.arrangement is not original
    assert score.ppq == 960 and score.tempo_us == 500000
    assert [(p.stem, p.channel) for p in score.parts] == [
        ("vocals", 0),
        ("drums", 9),
        ("bass", 1),
        ("other", 2),
    ]
    drum = score.parts[1].notes
    assert [(n.source_index, n.source_peak_index, n.pitch) for n in drum] == [
        (0, 0, 51),
        (1, 2, 36),
    ]
    for index, note in enumerate(drum):
        onset = Fraction([1792, 256][index] * 1000000, 44100)
        tick = (onset * 1920 / 1000000 + Fraction(1, 2)).numerator // (
            onset * 1920 / 1000000 + Fraction(1, 2)
        ).denominator
        assert time_fraction(note.start.original_us) == onset
        assert note.start.tick == tick
        assert Fraction(note.start.error_us.numerator, note.start.error_us.denominator) == (
            Fraction(tick * 1000000, 1920) - onset
        )
        assert time_fraction(note.end.original_us) - onset == 50000
        assert note.velocity == 96
    assert score.end_tick >= max(n.end.tick for p in score.parts for n in p.notes)
    raw = encode_estimated_midi(score)
    verify_estimated_midi(raw, score)
    midi = mido.MidiFile(file=BytesIO(raw))
    assert midi.type == 1 and midi.ticks_per_beat == 960 and len(midi.tracks) == 5
    assert sum(m.type == "note_on" for t in midi.tracks for m in t) == 5
    assert not any(
        m.type in {"program_change", "control_change", "pitchwheel", "time_signature"}
        for t in midi.tracks
        for m in t
    )
    assert [sum(m.time for m in t) for t in midi.tracks] == [score.end_tick] * 5
    assert score.writer_eligibility == "blocked" and not score.execution_allowed
    assert set(original.blockers).issubset(score.blockers)
    assert "pitch-bends-not-rendered" in score.blockers


def test_all_nine_explicit_preview_keys_preserve_occurrences():
    source = inputs()
    seed = source.drums.peaks[2]
    peaks = [seed.model_copy(update=dict(id=f"{label}.7", label=label)) for label in DRUM_CLASSES]
    source.drums = EstimatedDrumInput.model_validate(
        {
            **source.drums.model_dump(),
            "peaks": peaks,
            "rejected_peaks": [],
            "events": [
                ScoredDrum(id=p.id, label=p.label, microseconds=source.drums.events[1].microseconds)
                for p in peaks
            ],
        }
    )
    score = project_estimated_midi(build_percussion_arrangement(source))
    assert [n.pitch for n in score.parts[1].notes] == [49, 51, 42, 46, 36, 38, 43, 48, 47]
    assert [n.source_index for n in score.parts[1].notes] == list(range(9))
    verify_estimated_midi(encode_estimated_midi(score), score)


def test_nested_same_key_is_rejected_instead_of_fifo_repair():
    source = inputs()
    source.pitched = pitched_inputs(
        frames=2000,
        rate=48000,
        notes=[
            dict(start_frame=0, end_frame=3, pitch=60, activation=0.7, bend_offset=0),
            dict(start_frame=1, end_frame=2, pitch=60, activation=0.6, bend_offset=3),
        ],
    )
    with pytest.raises(ValueError, match="same-key"):
        project_estimated_midi(build_percussion_arrangement(source))


def test_short_final_row_cannot_be_silently_extended_on_tick_collapse():
    source = inputs()
    pitched = pitched_inputs(
        frames=559,
        rate=48000,
        notes=[dict(start_frame=1, end_frame=2, pitch=60, activation=0.7, bend_offset=0)],
    )
    frames = model_frame_count(559, 48000)
    drums = EstimatedDrumInput.model_validate(
        {
            **source.drums.model_dump(),
            "frames": 559,
            "model_frames": frames,
            "rows": drum_output_rows(frames),
            "peaks": [],
            "events": [],
            "rejected_peaks": [],
            "model_pcm": {**source.drums.model_pcm.model_dump(), "size_bytes": frames * 8},
        }
    )
    source = type(source).model_validate(
        {**source.model_dump(), "pitched": pitched, "drums": drums}
    )
    with pytest.raises(ValueError, match="collapse"):
        project_estimated_midi(build_percussion_arrangement(source))


@pytest.mark.parametrize("change", ["tempo", "channel", "note", "extra", "end", "trailing"])
def test_independent_verifier_rejects_complete_stream_mutations(change):
    score = project_estimated_midi(build_percussion_arrangement(inputs()))
    raw = encode_estimated_midi(score)
    midi = mido.MidiFile(file=BytesIO(raw))
    if change == "tempo":
        next(m for m in midi.tracks[0] if m.type == "set_tempo").tempo += 1
    elif change in {"channel", "note"}:
        msg = next(m for m in midi.tracks[1] if m.type == "note_on")
        setattr(msg, change, getattr(msg, change) + 1)
    elif change == "extra":
        midi.tracks[1].insert(1, mido.Message("control_change", control=64, value=127))
    elif change == "end":
        midi.tracks[1][-1].time += 1
    stream = BytesIO()
    midi.save(file=stream)
    altered = stream.getvalue() + (b"extra" if change == "trailing" else b"")
    with pytest.raises(ValueError):
        verify_estimated_midi(altered, score)


def test_untrusted_derived_parts_and_mutated_score_cannot_encode():
    record = build_percussion_arrangement(inputs())
    record.parts[0].notes.clear()
    with pytest.raises(ValueError):
        project_estimated_midi(record)
    score = project_estimated_midi(build_percussion_arrangement(inputs()))
    score.parts[0].notes[0].pitch += 1
    with pytest.raises(ValueError):
        encode_estimated_midi(score)


def test_empty_candidates_keep_trailing_source_duration_without_fake_notes():
    source = inputs()
    source.pitched = pitched_inputs(frames=2000, rate=48000, notes=[])
    source.drums = EstimatedDrumInput.model_validate(
        {**source.drums.model_dump(), "peaks": [], "events": [], "rejected_peaks": []}
    )
    score = project_estimated_midi(build_percussion_arrangement(source))
    assert all(not part.notes for part in score.parts)
    assert score.end_tick == 80
    assert time_fraction(score.source_end_us) == Fraction(2000 * 1000000, 48000)
    verify_estimated_midi(encode_estimated_midi(score), score)
