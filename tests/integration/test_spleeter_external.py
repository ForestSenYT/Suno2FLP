"""Explicit actual checkpoint probes; default tests never download or import a model."""

import os
import platform
import sys
from pathlib import Path

import pytest

from suno2flp.core.offline_files import verify_inputs
from suno2flp.integrations.spleeter_backend import provision_spleeter, verify_spleeter

pytestmark = pytest.mark.external


def test_native_checkpoint(tmp_path: Path) -> None:
    artifacts = os.environ.get("SUNO2FLP_SPLEETER_ARTIFACTS")
    if not artifacts:
        pytest.skip("Set SUNO2FLP_SPLEETER_ARTIFACTS to the fixed locally audited 55 artifacts")
    if sys.platform != "win32" or platform.python_version() != "3.11.16":
        pytest.skip("First Spleeter profile requires CPython3.11.16 Windows x64")
    record = provision_spleeter(tmp_path / "backend", Path(artifacts))
    first = verify_spleeter(record.root, tmp_path / "probe1")
    second = verify_spleeter(record.root, tmp_path / "probe2")
    assert first.native == second.native
    assert first.native.device_types == ["CPU"]
    assert first.model_qualification == "not_assessed" and not first.execution_allowed
    impulses = next(item for item in first.evidence if item.fixture == "impulses")
    assert impulses.impulse_peak_frames == [0, 6000, 12346]
    assert all(item.conservation_error <= 1e-12 for item in first.evidence)
    assert (
        next(item for item in first.evidence if item.fixture == "stereo-pattern").residual_peak > 0
    )
    verify_inputs(record.artifacts)
