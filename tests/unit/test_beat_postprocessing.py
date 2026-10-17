"""Independent preservation of raw peaks and upstream floating tie behavior."""

import struct
from fractions import Fraction

import pytest

from suno2flp.validator.beat_postprocessing import reconstruct_beats


def raw(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def test_adjacent_plateau_preserves_half_frame_and_alignment_audit() -> None:
    result = reconstruct_beats(raw([1, 1, -2, -2, -2, 2]), raw([-1, -1, 1, -1, -1, -1]))
    assert result.beat_peaks == [0, 1, 5]
    assert result.beat_frames == [Fraction(1, 2), Fraction(5)]
    assert result.downbeat_frames == [Fraction(2)]
    assert result.aligned_downbeat_frames == [Fraction(1, 2)]
    assert result.downbeat_to_beat == [0]


def test_float_seconds_tie_is_not_replaced_by_rational_distance() -> None:
    beats = [-1.0] * 7
    beats[2] = beats[6] = 1
    downbeats = [-1.0] * 7
    downbeats[4] = 1
    result = reconstruct_beats(raw(beats), raw(downbeats))
    # Rational distances both equal2; binary64 seconds make frame6 closer.
    assert result.downbeat_to_beat == [1]


def test_downbeat_only_is_preserved_without_inventing_beats() -> None:
    result = reconstruct_beats(raw([-2] * 5), raw([1, -2, -2, -2, -2]))
    assert result.beat_frames == []
    assert result.downbeat_to_beat == [None]
    assert result.aligned_downbeat_frames == [Fraction(0)]


def test_zero_logits_do_not_become_beats() -> None:
    result = reconstruct_beats(raw([0] * 4), raw([0] * 4))
    assert result.beat_frames == result.aligned_downbeat_frames == []


@pytest.mark.parametrize("invalid", [b"", b"x", raw([float("nan")]), raw([float("inf")])])
def test_incomplete_or_nonfinite_logits_fail(invalid: bytes) -> None:
    with pytest.raises(ValueError):
        reconstruct_beats(invalid, invalid)


def test_mismatched_lengths_fail() -> None:
    with pytest.raises(ValueError):
        reconstruct_beats(raw([1]), raw([1, 2]))
