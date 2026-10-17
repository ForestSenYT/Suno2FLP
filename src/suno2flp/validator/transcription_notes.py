"""Projection of estimated model frame indices, never a source MIDI transformation."""

from fractions import Fraction

from suno2flp.core.note_scoring import ScoredNote
from suno2flp.core.performance import RationalTime
from suno2flp.core.transcription import InferredFrameNote
from suno2flp.core.transcription_clock import (
    MODEL_RATE,
    owned_prediction_rows,
    resampled_frame_count,
)


def frame_notes_to_scored(
    notes: list[InferredFrameNote], resampled_frames: int, source_frames: int, source_rate: int
) -> list[ScoredNote]:
    if resampled_frames != resampled_frame_count(source_frames, source_rate):
        raise ValueError("Derived clock disagrees with original source clock")
    rows = owned_prediction_rows(resampled_frames)
    result = []
    for index, declared in enumerate(notes):
        note = InferredFrameNote.model_validate(declared.model_dump())
        if note.end_frame > len(rows):
            raise ValueError("Estimated note extends beyond complete source frame evidence")
        start = Fraction(rows[note.start_frame].source_sample * 1_000_000, MODEL_RATE)
        end = (
            Fraction(rows[note.end_frame].source_sample * 1_000_000, MODEL_RATE)
            if note.end_frame < len(rows)
            else Fraction(source_frames * 1_000_000, source_rate)
        )
        result.append(
            ScoredNote(
                id=f"bp-note-{index:05d}",
                pitch=note.pitch,
                onset_microseconds=RationalTime.exact(start),
                offset_microseconds=RationalTime.exact(end),
            )
        )
    return result
