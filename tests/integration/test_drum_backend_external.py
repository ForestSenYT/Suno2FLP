"""Explicit opt-in actual CPU encoder calls; no DAW or media download."""

import os
from pathlib import Path

import pytest

from suno2flp.integrations.drum_probe import probe_drum_backend


@pytest.mark.external
def test_actual_fixed_selected_drum_encoder(tmp_path: Path) -> None:
    root = os.environ.get("SUNO2FLP_DRUM_BACKEND")
    if not root:
        pytest.skip(
            "Set SUNO2FLP_DRUM_BACKEND to a current independently provisioned fixed local runtime"
        )
    report = probe_drum_backend(Path(root), tmp_path / "probe")
    assert len(report.fixtures) == 2
    assert all(f.results[0].files == f.results[1].files for f in report.fixtures)
    assert report.model_qualification == "not_assessed" and report.writer_eligibility == "blocked"
