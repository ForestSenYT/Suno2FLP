"""Original fixtures: complete continuous windows and original-clock observation only."""

import importlib
from fractions import Fraction

import pytest


def api():
    assert importlib.util.find_spec("suno2flp.core.yourmt3") is not None, "Missing isolated clock"
    return importlib.import_module("suno2flp.core.yourmt3")


def test_continuous_windows_include_short_tail_without_moving_origin():
    model = api()
    windows = model.plan_yourmt3_windows(98_304, 48_000)
    assert [(w.index, w.start_frame, w.valid_frames) for w in windows] == [
        (0, 0, 32_767),
        (1, 32_767, 1),
    ]
    assert Fraction(windows[1].start_frame * 48_000, 16_000) == 98_301
    assert windows[1].padding_frames == 32_766


@pytest.mark.parametrize(
    "frames,rate", [(0, 48000), (True, 48000), (1, 7999), (48000 * 601, 48000)]
)
def test_unbounded_or_non_integer_source_clock_is_rejected(frames, rate):
    with pytest.raises(ValueError):
        api().plan_yourmt3_windows(frames, rate)


def test_observation_is_half_open_and_keeps_tied_context_note():
    model = api()
    interval = model.FrameInterval(start_frame=48_000, end_frame=96_000)
    notes = [
        model.YourMT3Note(is_drum=False, program=100, pitch=60, onset=0.8, offset=1.3, velocity=1),
        model.YourMT3Note(is_drum=False, program=0, pitch=64, onset=1.5, offset=2.0, velocity=1),
        model.YourMT3Note(is_drum=True, program=128, pitch=36, onset=2.0, offset=2.01, velocity=1),
    ]
    summary = model.summarize_yourmt3(notes, [interval], 48_000)[0]
    assert summary.onsets == 1
    assert summary.overlapping_notes == 2
    assert summary.programs == {0: 1, 100: 1}
    assert summary.ground_truth_metrics == "reference_unavailable"
    assert notes[0].onset == 0.8  # Observation never crops or rewrites the native note.


def test_intervals_are_explicit_ordered_nonoverlapping_and_bounded():
    model = api()
    for pairs in ([(0, 0)], [(1, 5), (4, 8)], [(5, 7), (0, 4)], [(0, 11)]):
        with pytest.raises(ValueError):
            model.validate_yourmt3_intervals(
                [model.FrameInterval(start_frame=a, end_frame=b) for a, b in pairs], 10
            )


def test_more_notes_never_grant_music_or_writer_acceptance():
    model = api()
    note = model.YourMT3Note(is_drum=False, program=0, pitch=60, onset=0.1, offset=0.3, velocity=1)
    summary = model.summarize_yourmt3(
        [note] * 30, [model.FrameInterval(start_frame=0, end_frame=48000)], 48000
    )[0]
    assert summary.overlapping_notes == 30
    assert summary.musical_correctness == "not_assessed"
    assert summary.writer_eligibility == "blocked"
