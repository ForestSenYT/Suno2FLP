"""Opt-in current private artifacts; no model/DAW execution or private fixtures."""

import os
from pathlib import Path

import pytest

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline.estimated_arrangement import compose_estimated_arrangement
from suno2flp.validator.estimated_arrangement import verify_estimated_arrangement


@pytest.mark.external
def test_current_local_artifacts_compose_without_inference(tmp_path):
    if os.environ.get("SUNO2FLP_TEST_ESTIMATED_ARRANGEMENT") != "1":
        pytest.skip("Explicit local saved-artifact composition opt-in is required")
    batch = os.environ.get("SUNO2FLP_ESTIMATED_BATCH")
    if not batch or not Path(batch).is_file():
        pytest.skip("A current complete private stem batch is required")
    beats = os.environ.get("SUNO2FLP_ESTIMATED_BEATS")
    if beats and not Path(beats).is_file():
        pytest.skip("The explicitly selected private beat report is missing")
    output = tmp_path / "new-estimated-arrangement"
    record = compose_estimated_arrangement(
        Path(batch), output, beats_path=Path(beats) if beats else None
    )
    assert verify_estimated_arrangement(output / "estimated-arrangement.json") == record
    assert capture_stream_input(record.inputs.source_audio.path) == record.inputs.source_audio
    assert record.execution_allowed is False and record.ground_truth_metrics == "unavailable"
