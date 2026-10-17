"""Selected IDM encoder row centers, including negative and trailing padding.

Centered1024-FFT at hop256 follows right padding to a hop multiple. ConvNeXt's
stem time kernel7/pad3 has zero offset; three time kernel3/pad3/stride1 layers
each add4rows and move the row center by-2. Residual blocks and the head have
symmetric time padding. This defines geometric coordinates, not a calibrated
musical onset/latency correction.
"""

from fractions import Fraction
from typing import Literal

from suno2flp.core.separation_clock import MAX_MODEL_FRAMES, MODEL_RATE, model_frame_count

HOP = 256
LEADING_ROWS = 6
MAX_ROWS = (MAX_MODEL_FRAMES + HOP - 1) // HOP + 13
DrumDomain = Literal["source", "leading_padding", "tail_padding"]


def drum_output_rows(model_frames: int) -> int:
    if type(model_frames) is not int or not 513 <= model_frames <= MAX_MODEL_FRAMES:
        raise ValueError("Drum encoder requires513..26460000 model frames; no truncation")
    return (model_frames + HOP - 1) // HOP + 13


def drum_model_sample(row: int) -> int:
    if type(row) is not int or not 0 <= row < MAX_ROWS:
        raise ValueError("Drum row exceeds the fixed native address budget")
    return (row - LEADING_ROWS) * HOP


def drum_source_time(row: int) -> Fraction:
    """Signed exact original-clock microseconds; leading context is not clamped."""
    return Fraction(drum_model_sample(row) * 1_000_000, MODEL_RATE)


def drum_domain(row: int, source_frames: int, source_rate: int) -> DrumDomain:
    model_frames = model_frame_count(source_frames, source_rate)
    if row >= drum_output_rows(model_frames):
        raise ValueError("Drum row is outside the complete current native output")
    position = drum_model_sample(row)
    if position < 0:
        return "leading_padding"
    if Fraction(position, MODEL_RATE) >= Fraction(source_frames, source_rate):
        return "tail_padding"
    return "source"
