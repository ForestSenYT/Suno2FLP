"""Fixed unqualified peak profile; original/native data and all rejected peaks survive."""

import math
import struct
import sys
from array import array
from collections.abc import Callable
from typing import Literal

from suno2flp.core.drum_clock import (
    drum_domain,
    drum_model_sample,
    drum_output_rows,
    drum_source_time,
)
from suno2flp.core.drum_peaks import MAX_PEAKS, DrumPeak, RejectedDrumPeak
from suno2flp.core.drum_scoring import DRUM_CLASSES, MAX_DRUMS, ScoredDrum
from suno2flp.core.errors import OfflineError
from suno2flp.core.performance import RationalTime
from suno2flp.core.separation_clock import model_frame_count


def derive_drum_peaks(
    onset_raw: bytes,
    velocity_raw: bytes,
    source_frames: int,
    source_rate: int,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[DrumPeak], list[ScoredDrum], list[RejectedDrumPeak]]:
    # Own byte snapshots before callbacks, including if called with mutable buffers.
    onset_raw, velocity_raw = bytes(onset_raw), bytes(velocity_raw)
    rows = drum_output_rows(model_frame_count(source_frames, source_rate))
    if len(onset_raw) != 9 * rows * 4 or len(velocity_raw) != 9 * rows * 4:
        raise ValueError(
            "Complete native drum arrays must contain all nine classes and padding rows"
        )

    def check() -> None:
        if should_cancel is not None and should_cancel():
            raise OfflineError("drum_peaks_cancelled", "Drum peak extraction cancelled")

    check()
    onsets, velocities = array("f"), array("f")
    if onsets.itemsize != 4:
        raise ValueError("Drum parsing requires IEEE float32 arrays")
    onsets.frombytes(onset_raw)
    velocities.frombytes(velocity_raw)
    if sys.byteorder != "little":
        onsets.byteswap()
        velocities.byteswap()
    for index, (onset, velocity) in enumerate(zip(onsets, velocities, strict=True)):
        if index % 1024 == 0:
            check()
        if not math.isfinite(onset) or not math.isfinite(velocity) or not 0 < velocity <= 2.0:
            raise ValueError("Nonfinite or out-of-profile native drum activation")
    peaks = []
    events = []
    rejected = []
    for class_index, label in enumerate(DRUM_CLASSES):
        start = class_index * rows
        for row in range(rows):
            if row % 1024 == 0:
                check()
            value = onsets[start + row]
            left = onsets[start + row - 1] if row else -math.inf
            right = onsets[start + row + 1] if row + 1 < rows else -math.inf
            if not (value > 0 and value > left and value >= right):
                continue
            offset = (start + row) * 4
            domain = drum_domain(row, source_frames, source_rate)
            peak = DrumPeak(
                id=f"{label}.{row}",
                label=label,
                row=row,
                model_sample=drum_model_sample(row),
                domain=domain,
                logit_bits=struct.unpack("<I", onset_raw[offset : offset + 4])[0],
                velocity_bits=struct.unpack("<I", velocity_raw[offset : offset + 4])[0],
            )
            peaks.append(peak)
            if domain == "source":
                events.append(
                    ScoredDrum(
                        id=peak.id,
                        label=label,
                        microseconds=RationalTime.exact(drum_source_time(row)),
                    )
                )
            else:
                reason: Literal["before-source-zero", "at-or-after-original-end"] = (
                    "before-source-zero"
                    if domain == "leading_padding"
                    else "at-or-after-original-end"
                )
                rejected.append(RejectedDrumPeak(peak=peak, reason=reason))
            if len(peaks) > MAX_PEAKS or len(events) > MAX_DRUMS:
                raise OfflineError(
                    "drum_peak_limit", "Complete drum peaks exceed budget; no truncation"
                )
    check()
    return peaks, events, rejected
