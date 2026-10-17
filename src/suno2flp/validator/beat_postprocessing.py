"""Standard-library replay of fixed minimal peak picking, without model imports."""

import math
import struct
from bisect import bisect_left
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class BeatPeaks:
    beat_peaks: list[int]
    downbeat_peaks: list[int]
    beat_frames: list[Fraction]
    downbeat_frames: list[Fraction]
    downbeat_to_beat: list[int | None]
    aligned_downbeat_frames: list[Fraction]


def _peaks(raw: bytes) -> list[int]:
    values = [v[0] for v in struct.iter_unpack("<f", raw)]
    if any(not math.isfinite(v) for v in values):
        raise ValueError("Nonfinite rhythm logits")
    return [i for i, v in enumerate(values) if v > 0 and v == max(values[max(0, i - 3) : i + 4])]


def _deduplicate(peaks: list[int]) -> list[Fraction]:
    result: list[Fraction] = []
    count = 0
    for peak in peaks:
        # Upstream compares against the running mean, rather than the last peak.
        if result and peak - result[-1] <= 1:
            result[-1] = (result[-1] * count + peak) / (count + 1)
            count += 1
        else:
            result.append(Fraction(peak))
            count = 1
    return result


def reconstruct_beats(beat: bytes, downbeat: bytes) -> BeatPeaks:
    if not beat or len(beat) != len(downbeat) or len(beat) % 4 or len(beat) > 30002 * 4:
        raise ValueError("Expected complete equal bounded float32 rhythm logits")
    bp, dp = _peaks(beat), _peaks(downbeat)
    bf, df = _deduplicate(bp), _deduplicate(dp)
    # Reproduce NumPy's binary64 seconds subtraction and first argmin tie rule.
    # Exact rational coordinates are retained separately; no inverse float timing.
    times = [float(f) / 50 for f in bf]
    mapping: list[int | None] = []
    for d in df:
        seconds = float(d) / 50
        index = bisect_left(times, seconds)
        neighbours = [i for i in (index - 1, index) if 0 <= i < len(times)]
        mapping.append(
            min(neighbours, key=lambda i: abs(times[i] - seconds)) if neighbours else None
        )
    aligned = sorted({bf[i] if i is not None else d for d, i in zip(df, mapping, strict=True)})
    return BeatPeaks(bp, dp, bf, df, mapping, aligned)
