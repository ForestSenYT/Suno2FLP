"""Estimated notes use original sample-clock anchors, including the short window seam."""

from fractions import Fraction

import pytest

from suno2flp.core.note_scoring import time_fraction
from suno2flp.core.transcription import InferredFrameNote
from suno2flp.validator.transcription_notes import frame_notes_to_scored


def test_seam_and_last_offset_are_expressed_in_the_original_source_clock() -> None:
    notes = [
        InferredFrameNote(start_frame=140, end_frame=143, pitch=60, activation=0.7, bend_offset=0)
    ]
    converted = frame_notes_to_scored(notes, 36165, 36165, 22050)
    assert time_fraction(converted[0].onset_microseconds) == Fraction(35840 * 1000000, 22050)
    assert time_fraction(converted[0].offset_microseconds) == Fraction(36165 * 1000000, 22050)
    assert converted[0].id == "bp-note-00000"


def test_subsample_resampled_end_uses_source_duration_without_rounding() -> None:
    notes = [InferredFrameNote(start_frame=0, end_frame=1, pitch=60, activation=0.7, bend_offset=0)]
    assert time_fraction(
        frame_notes_to_scored(notes, 1, 1, 48000)[0].offset_microseconds
    ) == Fraction(1000000, 48000)
    with pytest.raises(ValueError, match="clock"):
        frame_notes_to_scored(notes, 2, 1, 48000)
