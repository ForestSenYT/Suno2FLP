"""Exact coordinates for the fixed 50Hz inferred beat grid, including half frames."""

from fractions import Fraction
from typing import Literal

from suno2flp.core.models import Contract
from suno2flp.core.performance import RationalTime

BEAT_FPS = 50
BEAT_RATE = 22050
BEAT_FFT = 1024
BEAT_HOP = 441
BEAT_CHUNK = 1500
BEAT_BORDER = 6


class BeatAnchor(Contract):
    analysis_frame: RationalTime
    source_sample: RationalTime
    microseconds: RationalTime
    domain: Literal["source", "padding"]


def beat_anchor(frame: Fraction, *, sample_rate: int, source_frames: int) -> BeatAnchor:
    if (
        type(sample_rate) is not int
        or not 8000 <= sample_rate <= 192000
        or type(source_frames) is not int
        or not 1 <= source_frames <= sample_rate * 600
    ):
        raise ValueError("Unsupported original source clock")
    # The fixed native deduplicator averages adjacent integer peaks. Its outputs
    # are integers or half frames; a floating timestamp is not an exact input.
    last_frame = (source_frames * BEAT_FPS + sample_rate - 1) // sample_rate
    if (
        type(frame) is not Fraction
        or frame.denominator not in (1, 2)
        or not 0 <= frame <= last_frame
    ):
        raise ValueError("Expected an exact integer/half analysis frame within the source grid")
    sample = frame * sample_rate / BEAT_FPS
    return BeatAnchor(
        analysis_frame=RationalTime.exact(frame),
        source_sample=RationalTime.exact(sample),
        microseconds=RationalTime.exact(frame * 1_000_000 / BEAT_FPS),
        domain="source" if sample < source_frames else "padding",
    )
