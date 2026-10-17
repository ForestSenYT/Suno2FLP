"""Separation runtime evidence never grants song, model or writer qualification."""

import importlib

import pytest
from pydantic import ValidationError


def test_large_native_artifact_has_a_separate_bounded_profile() -> None:
    contracts = importlib.import_module("suno2flp.core.separation_runtime")
    from suno2flp.core.transcription import ModelArtifactPin

    raw = dict(
        distribution="native",
        version="1",
        filename="native.whl",
        url="https://files.pythonhosted.org/packages/native.whl",
        size_bytes=272888761,
        sha256="a" * 64,
        license="Apache-2.0",
        notices={},
    )
    assert contracts.SeparationArtifactPin(**raw).size_bytes == 272888761
    with pytest.raises(ValidationError):
        ModelArtifactPin(**raw)
    with pytest.raises(ValidationError):
        contracts.SeparationArtifactPin(**{**raw, "size_bytes": 512 * 1024**2 + 1})


def test_native_probe_requires_complete_stereo_outputs_and_two_runs() -> None:
    contracts = importlib.import_module("suno2flp.core.separation_runtime")
    raw = dict(
        fixture="stereo-pattern",
        frames=44117,
        hashes={name: ["a" * 64, "a" * 64] for name in ("vocals", "drums", "bass", "other")},
    )
    evidence = contracts.SeparationFixtureResult(**raw)
    assert evidence.sample_rate == 44100 and evidence.channels == 2
    for changes in (
        {"frames": 44116},
        {"hashes": {"vocals": ["a" * 64, "a" * 64]}},
        {"hashes": {**raw["hashes"], "vocals": ["a" * 64, "b" * 64]}},
        {"sample_rate": 48000},
    ):
        with pytest.raises(ValidationError):
            contracts.SeparationFixtureResult(**{**raw, **changes})


def test_backend_cannot_promote_native_preparation_to_qualification(tmp_path) -> None:
    contracts = importlib.import_module("suno2flp.core.separation_runtime")
    identity = dict(path=tmp_path / "python.exe", sha256="a" * 64, size_bytes=1, mtime_ns=1)
    raw = dict(
        root=tmp_path, python=identity, runtime=[identity], artifacts=[], adapters=[], payload={}
    )
    record = contracts.SpleeterBackend(**raw)
    assert record.model_qualification == "not_assessed" and record.writer_eligibility == "blocked"
    assert record.execution_allowed is False
    for changes in (
        {"model_qualification": "qualified"},
        {"execution_allowed": True},
        {"writer_eligibility": "eligible"},
        {"curated_install": "upstream-default"},
    ):
        with pytest.raises(ValidationError):
            contracts.SpleeterBackend(**{**raw, **changes})
