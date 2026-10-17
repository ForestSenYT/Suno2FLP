"""Preparation rejects missing prerequisites before starting a native child."""

from pathlib import Path

import pytest

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.transcription import BasicPitchProbe
from suno2flp.integrations.basic_pitch_backend import (
    check_artifact,
    load_basic_pitch_pins,
    provision_basic_pitch,
    read_basic_pitch,
    validate_basic_pitch_probe,
)


def test_fixed_recipe_contains_audited_model_source_and_notices() -> None:
    pins = load_basic_pitch_pins()
    assert len(pins.artifacts) == 42
    assert len(pins.source_correspondence) == 28
    assert pins.model_sha256 == "2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec"
    assert all(
        p.filename.endswith(".whl") or p.distribution == "pretty-midi" for p in pins.artifacts
    )
    assert not any(p.distribution.startswith("tensorflow") for p in pins.artifacts)
    assert any(p.distribution == "setuptools" and p.version == "80.9.0" for p in pins.artifacts)
    assert pins.supplemental_notice.filename == "flatbuffers-LICENSE.txt"


def test_altered_artifact_size_or_hash_fails(tmp_path: Path) -> None:
    path = tmp_path / "fake.whl"
    path.write_bytes(b"fake")
    pin = load_basic_pitch_pins().artifacts[0]
    with pytest.raises(ValueError, match="size/hash"):
        check_artifact(capture_stream_input(path), pin)
    pin = pin.model_copy(update={"size_bytes": 4})
    with pytest.raises(ValueError, match="size/hash"):
        check_artifact(capture_stream_input(path), pin)


def test_existing_output_and_missing_backend_are_explicit(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises((ValueError, FileExistsError)):
        provision_basic_pitch(output, tmp_path)
    assert list(output.iterdir()) == []
    with pytest.raises((ValueError, FileNotFoundError)):
        read_basic_pitch(tmp_path / "missing")


@pytest.mark.parametrize("mutation", ["shape", "version", "external", "missing-module"])
def test_native_handshake_requires_real_fixed_shapes_versions_and_module_inventory(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path / "backend"
    names = (
        "numpy",
        "onnxruntime",
        "scipy",
        "basic_pitch",
        "librosa",
        "pretty_midi",
        "mir_eval",
        "resampy",
    )
    raw = {
        "profile": "basic-pitch-native-probe-v1",
        "provider": "CPUExecutionProvider",
        "intra_op_threads": 8,
        "inter_op_threads": 1,
        "sequential": True,
        "repeatable": True,
        "shapes": {"note": [1, 172, 88], "onset": [1, 172, 88], "contour": [1, 172, 264]},
        "versions": {
            "onnxruntime": "1.23.2",
            "numpy": "2.3.5",
            "scipy": "1.16.3",
            "basic-pitch": "0.4.0",
        },
        "modules": {name: str(root / "packages" / name / "__init__.py") for name in names},
    }
    probe = BasicPitchProbe.model_validate(raw)
    validate_basic_pitch_probe(probe, root)
    if mutation == "shape":
        probe.shapes["note"] = [1, 171, 88]
    elif mutation == "version":
        probe.versions["onnxruntime"] = "different"
    elif mutation == "external":
        probe.modules["numpy"] = tmp_path / "system/numpy.py"
    else:
        del probe.modules["numpy"]
    with pytest.raises(ValueError):
        validate_basic_pitch_probe(probe, root)
