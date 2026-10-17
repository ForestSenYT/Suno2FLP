"""Original raw logits test explicit unqualified peak extraction and padding audit."""

import struct
from fractions import Fraction

import pytest

from suno2flp.core.drum_clock import drum_output_rows
from suno2flp.core.drum_scoring import DRUM_CLASSES
from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import time_fraction
from suno2flp.validator.drum_postprocessing import derive_drum_peaks


def raw_arrays(changes):
    rows = drum_output_rows(1024)
    onset = [-1.0] * (9 * rows)
    for label, row, value in changes:
        onset[DRUM_CLASSES.index(label) * rows + row] = value
    return struct.pack(f"<{len(onset)}f", *onset), struct.pack(
        f"<{len(onset)}f", *([0.5] * len(onset))
    )


def test_source_and_both_padding_sides_preserved_with_exact_bits():
    raw, velocity = raw_arrays(
        [("KD", 0, 3.0), ("KD", 6, 1.0), ("KD", 7, 2.0), ("KD", 10, 4.0), ("SD", 8, 1.0)]
    )
    peaks, events, rejected = derive_drum_peaks(raw, velocity, 1024, 44100)
    assert [(p.label, p.row, p.domain) for p in peaks] == [
        ("KD", 0, "leading_padding"),
        ("KD", 7, "source"),
        ("KD", 10, "tail_padding"),
        ("SD", 8, "source"),
    ]
    assert [e.id for e in events] == ["KD.7", "SD.8"]
    assert time_fraction(events[0].microseconds) == Fraction(256 * 1_000_000, 44100)
    assert [(p.peak.id, p.reason) for p in rejected] == [
        ("KD.0", "before-source-zero"),
        ("KD.10", "at-or-after-original-end"),
    ]
    assert peaks[0].model_sample == -1536
    assert peaks[1].logit_bits == struct.unpack("<I", struct.pack("<f", 2.0))[0]
    assert peaks[1].velocity_bits == struct.unpack("<I", struct.pack("<f", 0.5))[0]


def test_zero_threshold_is_strict_and_plateau_tie_is_leftmost():
    raw, velocity = raw_arrays([("KD", 6, 1.0), ("KD", 7, 1.0), ("SD", 8, 0.0)])
    peaks, events, rejected = derive_drum_peaks(raw, velocity, 1024, 44100)
    assert [e.id for e in events] == ["KD.6"] and not rejected
    assert len(peaks) == 1


@pytest.mark.parametrize("change", ["truncated", "nonfinite_onset", "nonfinite_velocity"])
def test_all_raw_values_and_lengths_checked_even_outside_selected_peaks(change):
    raw, velocity = raw_arrays([])
    if change == "truncated":
        raw = raw[:-4]
    elif change == "nonfinite_onset":
        raw = struct.pack("<f", float("nan")) + raw[4:]
    else:
        velocity = struct.pack("<f", float("inf")) + velocity[4:]
    with pytest.raises(ValueError):
        derive_drum_peaks(raw, velocity, 1024, 44100)


def test_cancellation_has_no_derived_success():
    raw, velocity = raw_arrays([])
    with pytest.raises(OfflineError, match="cancel"):
        derive_drum_peaks(raw, velocity, 1024, 44100, should_cancel=lambda: True)
