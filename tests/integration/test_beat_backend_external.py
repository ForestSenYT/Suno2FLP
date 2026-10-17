"""Explicit opt-in actual CPU handshake, never a fake availability check."""

import os
from pathlib import Path

import pytest

from suno2flp.integrations.beat_probe import probe_beat_backend


@pytest.mark.external
def test_actual_fixed_beat_runtime(tmp_path: Path) -> None:
    root = os.environ.get("SUNO2FLP_BEAT_BACKEND")
    if not root:
        pytest.skip("Set SUNO2FLP_BEAT_BACKEND to an independently provisioned fixed local backend")
    report = probe_beat_backend(Path(root), tmp_path / "probe")
    assert len(report.fixtures) == 4
    assert report.writer_eligibility == "blocked"
