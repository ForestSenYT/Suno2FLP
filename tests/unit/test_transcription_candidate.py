"""Candidates keep frame coordinates and do not certify musical correctness."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from suno2flp.core.transcription import InferredFrameNote, RawPredictionArtifact


def identity(tmp_path: Path, size: int) -> dict[str, object]:
    return {"path": tmp_path / "raw.f32", "sha256": "0" * 64, "size_bytes": size, "mtime_ns": 0}


def test_raw_dimensions_and_bytes_must_cover_complete_windows(tmp_path: Path) -> None:
    result = RawPredictionArtifact(
        kind="note", windows=2, file=identity(tmp_path, 2 * 172 * 88 * 4)
    )
    assert result.width == 88
    with pytest.raises(ValidationError, match="size"):
        RawPredictionArtifact(kind="contour", windows=2, file=identity(tmp_path, 2 * 172 * 88 * 4))


def test_notes_preserve_overlapping_bends_and_model_activation() -> None:
    note = InferredFrameNote(start_frame=10, end_frame=20, pitch=60, activation=0.7, bend_offset=10)
    assert note.bend_count == 10
    assert note.model_activation_is_confidence is False
    for update in (
        {"end_frame": 10},
        {"activation": float("nan")},
        {"start_frame": True},
        {"pitch": 109},
    ):
        with pytest.raises(ValidationError):
            InferredFrameNote.model_validate({**note.model_dump(), **update})
