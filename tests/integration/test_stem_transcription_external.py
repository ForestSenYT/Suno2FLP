"""Explicitly opted-in complete native pitched-stem candidate/replay; no DAW."""

import os
from pathlib import Path

import pytest

from suno2flp.pipeline.stem_transcription import transcribe_stems
from suno2flp.validator.stem_transcription import verify_stem_batch


@pytest.mark.external
def test_current_native_stem_transcription_and_complete_replay(tmp_path):
    source = os.environ.get("SUNO2FLP_STEM_SEPARATION_REPORT")
    backend = os.environ.get("SUNO2FLP_STEM_BASIC_PITCH_BACKEND")
    if not source or not backend:
        pytest.skip("Set SUNO2FLP_STEM_SEPARATION_REPORT and SUNO2FLP_STEM_BASIC_PITCH_BACKEND")
    result = transcribe_stems(Path(source), Path(backend), tmp_path / "candidate")
    assert [entry.stem for entry in result.stems] == ["vocals", "bass", "other"]
    assert not result.execution_allowed and result.model_qualification == "not_assessed"
    assert (
        verify_stem_batch(tmp_path / "candidate/stem-transcription.json", tmp_path / "replay")
        == result
    )
