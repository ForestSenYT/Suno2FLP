"""Original source positions, including half-frame peaks from native deduplication."""

from fractions import Fraction

import pytest

from suno2flp.core.beat_clock import beat_anchor


@pytest.mark.parametrize(
    ("rate", "frame", "samples", "microseconds"),
    [
        (48000, Fraction(1), Fraction(960), Fraction(20000)),
        (44100, Fraction(1), Fraction(882), Fraction(20000)),
        (11025, Fraction(1), Fraction(441, 2), Fraction(20000)),
        (11025, Fraction(1, 2), Fraction(441, 4), Fraction(10000)),
        (8000, Fraction(3, 2), Fraction(240), Fraction(30000)),
        (192000, Fraction(1, 2), Fraction(1920), Fraction(10000)),
    ],
)
def test_clock_preserves_fractional_source_positions(rate, frame, samples, microseconds):
    point = beat_anchor(frame, sample_rate=rate, source_frames=rate)
    assert Fraction(point.source_sample.numerator, point.source_sample.denominator) == samples
    assert Fraction(point.microseconds.numerator, point.microseconds.denominator) == microseconds
    assert point.domain == "source"


def test_terminal_padding_is_retained_and_not_clamped_to_last_source_sample():
    point = beat_anchor(Fraction(50), sample_rate=44100, source_frames=44099)
    assert point.domain == "padding"
    assert point.source_sample.numerator == 44100 and point.source_sample.denominator == 1
    assert point.microseconds.numerator == 1000000


@pytest.mark.parametrize("frame", [Fraction(-1), Fraction(1, 3), Fraction(51), 0.5, True])
def test_foreign_or_inexact_analysis_coordinates_are_rejected(frame):
    with pytest.raises(ValueError):
        beat_anchor(frame, sample_rate=48000, source_frames=48000)


@pytest.mark.parametrize(
    "rate,frames", [(True, 1), (7999, 1), (192001, 1), (48000, 0), (8000, 4800001)]
)
def test_clock_rejects_unsupported_source_geometry(rate, frames):
    with pytest.raises(ValueError):
        beat_anchor(Fraction(0), sample_rate=rate, source_frames=frames)
