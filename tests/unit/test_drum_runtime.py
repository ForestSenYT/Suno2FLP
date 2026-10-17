"""Pinned metadata is inert; no native imports/downloads in the application."""

import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from suno2flp.core.drum_scoring import DRUM_CLASSES
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.integrations.drum_backend import load_drum_pins
from suno2flp.integrations.drum_source import drum_payload


def test_fixed_license_complete_encoder_recipe():
    pins = load_drum_pins()
    assert pins.revision == "456656868538205ef756912c7cf5b0fd936de8af"
    assert pins.source.sha256 == "7ed64f8cc064055e80a694bba1013c15a23dc6d962b8a91b08fadb1e47b95bef"
    assert (
        pins.checkpoint_sha256 == "5856a9bee7c6d503842795756d238dc8470f6f3e010e9e4f33ede0362850cb4c"
    )
    assert len(pins.artifacts) == 13
    assert {p.distribution for p in pins.artifacts} == {
        "torch",
        "torchaudio",
        "numpy",
        "einops",
        "filelock",
        "fsspec",
        "jinja2",
        "markupsafe",
        "mpmath",
        "networkx",
        "setuptools",
        "sympy",
        "typing-extensions",
    }
    assert all(p.notices and p.sha256 and p.url.startswith("https://") for p in pins.artifacts)
    assert pins.classes == list(DRUM_CLASSES)
    assert len(pins.state) == 330
    assert sum(k.startswith("encoder.") for k in pins.state) == 194
    assert all(p.dtype == "float32" for p in pins.state.values())
    assert pins.source.license == "Apache-2.0"
    assert (
        pins.notices[0].sha256 == "da6d3703ed11cbe42bd212c725957c98da23cbff1998c05fa4b3d976d1a58e93"
    )
    assert set(pins.source_files) == {
        "idm/__init__.py",
        "idm/feature_extractor/encoder.py",
        "idm/feature_extractor/convnext.py",
        "idm/feature_extractor/mel.py",
        "idm/feature_extractor/stft.py",
        "idm/synthesis_conditioning/embedding.py",
        "idm/synthesis_conditioning/transcription.py",
        "idm/utils.py",
        "LICENSE",
        pins.checkpoint_path,
        pins.config_path,
    }
    helper = Path(__file__).parents[2] / "src/suno2flp/integrations/drum_activations.py"
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == pins.helper_sha256


@pytest.fixture
def synthetic_recipe(tmp_path):
    """Only test the inert installer algorithm; never qualify this dummy model."""
    pins = load_drum_pins().model_copy(deep=True)
    inputs = []
    for i, pin in enumerate(pins.artifacts):
        path = tmp_path / pin.filename
        notice = f"authored wheel notice{i}".encode()
        name = f"fixture{i}/LICENSE"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, notice)
            archive.writestr(f"fixture{i}/__init__.py", b"# original inert fixture\n")
        identity = capture_stream_input(path)
        pin.size_bytes, pin.sha256 = identity.size_bytes, identity.sha256
        pin.notices = {name: hashlib.sha256(notice).hexdigest()}
        pin.omitted_members = {}
        inputs.append(identity)
    content = {name: b"# original inert selected file\n" for name in pins.source_files}
    content["idm/synthesis_conditioning/transcription.py"] = (
        b"from idm.utils import get_act_functional, get_act_module\n"
    )
    # Dummy bytes are never parsed as weights or executed, and are not a real backend.
    content[pins.checkpoint_path] = b"not a usable checkpoint"
    content["idm/decoder/never_import.py"] = b"raise RuntimeError('not selected')\n"
    path = tmp_path / pins.source.filename
    with tarfile.open(path, "w:gz") as archive:
        for name, raw in content.items():
            info = tarfile.TarInfo(pins.source_prefix + name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    identity = capture_stream_input(path)
    pins.source.size_bytes, pins.source.sha256 = identity.size_bytes, identity.sha256
    pins.source.source_inventory = sorted(pins.source_prefix + name for name in content)
    pins.source_files = {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in content.items()
        if name != "idm/decoder/never_import.py"
    }
    pins.source.notices = {pins.source_prefix + "LICENSE": pins.source_files["LICENSE"]}
    raw = content["idm/synthesis_conditioning/transcription.py"].replace(
        b"from idm.utils", b"from idm.audit_activations"
    )
    pins.patched_transcription_sha256 = hashlib.sha256(raw).hexdigest()
    inputs.append(identity)
    path = tmp_path / pins.notices[0].filename
    path.write_bytes(b"original synthetic MIT notice")
    identity = capture_stream_input(path)
    pins.notices[0].size_bytes, pins.notices[0].sha256 = identity.size_bytes, identity.sha256
    inputs.append(identity)
    return pins, inputs


def test_inert_payload_selects_only_encoder_and_exact_patch(synthetic_recipe, tmp_path):
    pins, inputs = synthetic_recipe
    before = [capture_stream_input(i.path) for i in inputs]
    expected = drum_payload(pins, inputs)
    destination = tmp_path / "packages"
    destination.mkdir()
    actual = drum_payload(pins, inputs, destination)
    assert expected == actual
    assert "idm/utils.py" not in actual
    assert not any("decoder/" in name for name in actual)
    assert {
        "models/idm.ckpt",
        "models/idm-model.yaml",
        "licenses/IDM-Apache-2.0.txt",
        "licenses/ConvNeXt-MIT.txt",
        "idm/audit_activations.py",
    } <= actual.keys()
    assert (
        b"from idm.audit_activations"
        in (destination / "idm/synthesis_conditioning/transcription.py").read_bytes()
    )
    assert before == [capture_stream_input(i.path) for i in inputs]
    with pytest.raises(FileExistsError):
        drum_payload(pins, inputs, destination)


@pytest.mark.parametrize(
    "change", ["missing", "source_hash", "selected_hash", "patch", "notice", "helper", "collision"]
)
def test_changed_recipe_or_artifacts_fail(synthetic_recipe, change):
    pins, inputs = synthetic_recipe
    if change == "missing":
        inputs = inputs[:-1]
    elif change == "source_hash":
        pins.source.sha256 = "0" * 64
    elif change == "selected_hash":
        pins.source_files["idm/feature_extractor/encoder.py"] = "0" * 64
    elif change == "patch":
        pins.patched_transcription_sha256 = "0" * 64
    elif change == "notice":
        pins.notices[0].sha256 = "0" * 64
    elif change == "helper":
        pins.helper_sha256 = "0" * 64
    else:
        pins.notices[0].target = "models/idm.ckpt"
    expected = {
        "missing": "requires13",
        "source_hash": "Fixed artifact",
        "selected_hash": "Selected drum",
        "patch": "source patch",
        "notice": "MIT notice",
        "helper": "activation helper",
        "collision": "collide",
    }
    with pytest.raises(ValueError, match=expected[change]):
        drum_payload(pins, inputs)
