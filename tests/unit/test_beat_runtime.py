"""Offline runtime boundaries do not require Torch, models or a DAW."""

import hashlib
import importlib
import json
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from suno2flp.core.beat_runtime import BeatBackend, BeatExecution
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.integrations.beat_backend import load_beat_pins, provision_beat_backend


def test_recipe_contains_the_complete_matched_cpu_closure() -> None:
    pins = load_beat_pins()
    versions = {p.distribution: p.version for p in pins.artifacts}
    assert len(versions) == 19
    assert versions["torch"] == versions["torchaudio"] == "2.11.0+cpu"
    assert pins.model.sha256 == "8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331"
    assert len(pins.model_geometry) == 166
    assert pins.source_correspondence
    assert all(p.notices for p in pins.artifacts)


def test_missing_artifacts_does_not_create_backend(tmp_path: Path) -> None:
    output = tmp_path / "backend"
    with pytest.raises((ValueError, FileNotFoundError)):
        provision_beat_backend(output, tmp_path / "missing")
    assert not output.exists()


def test_existing_output_is_never_touched(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        provision_beat_backend(tmp_path, tmp_path / "missing")
    assert sentinel.read_bytes() == b"original"


@pytest.mark.parametrize("field,value", [("intra_op_threads", 1), ("mkldnn", True), ("cuda", "12")])
def test_foreign_execution_cannot_be_promoted(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        BeatExecution.model_validate({field: value})


def test_backend_does_not_grant_quality_or_writer_eligibility() -> None:
    fields = BeatBackend.model_fields
    assert fields["model_qualification"].default == "not_assessed"
    assert fields["writer_eligibility"].default == "blocked"


@pytest.fixture
def recipe(tmp_path, monkeypatch):
    backend = importlib.import_module("suno2flp.integrations.beat_backend")
    raw = backend.load_beat_pins().model_dump()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for i, pin in enumerate(raw["artifacts"]):
        path = artifacts / pin["filename"]
        notice = f"pkg{i}/LICENSE"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(f"pkg{i}/code.py", b"# synthetic original package")
            archive.writestr(notice, b"original test notice")
        identity = capture_stream_input(path)
        pin.update(
            size_bytes=identity.size_bytes,
            sha256=identity.sha256,
            notices={notice: hashlib.sha256(b"original test notice").hexdigest()},
            omitted_members={},
        )
    raw["source_correspondence"] = {}
    model = artifacts / raw["model"]["filename"]
    model.write_bytes(b"original inert checkpoint; never executed")
    identity = capture_stream_input(model)
    raw["model"].update(size_bytes=identity.size_bytes, sha256=identity.sha256)
    pins = backend.BeatPins.model_validate(raw)
    runtime = tmp_path / "python.bin"
    runtime.write_bytes(b"original inert runtime; never executed")
    monkeypatch.setattr(backend, "load_beat_pins", lambda: pins)
    monkeypatch.setattr(
        backend,
        "_runtime",
        lambda: (capture_stream_input(runtime), [capture_stream_input(runtime)]),
    )
    monkeypatch.setattr(backend, "beat_adapters", lambda: [capture_stream_input(runtime)])
    return backend, artifacts, pins


def test_exclusive_preparation_and_current_read_preserve_artifacts(recipe, tmp_path) -> None:
    backend, artifacts, _ = recipe
    before = [capture_stream_input(p) for p in artifacts.iterdir()]
    record = backend.provision_beat_backend(tmp_path / "backend", artifacts)
    assert backend.read_beat_backend(record.root) == record
    assert len(record.artifacts) == 20
    assert before == [capture_stream_input(p) for p in artifacts.iterdir()]


@pytest.mark.parametrize("mutation", ["extra", "missing", "coherent-rehash"])
def test_changed_payload_cannot_be_promoted(recipe, tmp_path, mutation) -> None:
    backend, artifacts, _ = recipe
    record = backend.provision_beat_backend(tmp_path / "backend", artifacts)
    target = record.root / "packages/models/final0.ckpt"
    if mutation == "extra":
        (target.parent / "foreign.py").write_bytes(b"foreign")
    elif mutation == "missing":
        target.unlink()
    else:
        target.write_bytes(b"coherently rehashed, but not the pinned checkpoint")
        data = record.model_dump(mode="json")
        data["payload"]["models/final0.ckpt"] = capture_stream_input(target).sha256
        (record.root / "backend.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        backend.read_beat_backend(record.root)


def test_hostile_wheel_is_rejected_before_output(recipe, tmp_path) -> None:
    backend, artifacts, pins = recipe
    pin = pins.artifacts[0]
    path = artifacts / pin.filename
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("../escape.py", b"never extracted")
    identity = capture_stream_input(path)
    pin.size_bytes, pin.sha256 = identity.size_bytes, identity.sha256
    output = tmp_path / "refused"
    with pytest.raises(ValueError, match="Unsafe"):
        backend.provision_beat_backend(output, artifacts)
    assert not output.exists()


def test_cancellation_during_preparation_has_no_completion_marker(recipe, tmp_path) -> None:
    from suno2flp.core.audio_decode import DecodeCancelled

    backend, artifacts, _ = recipe
    root = tmp_path / "cancelled"
    with pytest.raises(DecodeCancelled):
        backend.provision_beat_backend(
            root, artifacts, should_cancel=lambda: (root / "packages").exists()
        )
    assert not (root / "backend.json").exists()
