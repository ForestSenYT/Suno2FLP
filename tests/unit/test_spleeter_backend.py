"""Real exclusive installation/current-file checks using tiny original fake archives."""

import hashlib
import importlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.separation_runtime import SpleeterPins


def test_prepare_and_read_require_explicit_prerequisites(tmp_path: Path) -> None:
    backend = importlib.import_module("suno2flp.integrations.spleeter_backend")
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises((ValueError, FileExistsError)):
        backend.provision_spleeter(existing, tmp_path)
    assert list(existing.iterdir()) == []
    with pytest.raises((ValueError, FileNotFoundError)):
        backend.read_spleeter(tmp_path / "missing")


@pytest.fixture
def recipe(tmp_path: Path, monkeypatch):
    backend = importlib.import_module("suno2flp.integrations.spleeter_backend")
    raw = backend.load_spleeter_pins().model_dump()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for i, pin in enumerate(raw["artifacts"]):
        path = artifacts / pin["filename"]
        module_names = {
            "numpy": "numpy",
            "tensorflow-intel": "tensorflow",
            "keras": "keras",
            "scipy": "scipy",
            "pandas": "pandas",
            "spleeter": "spleeter",
        }
        name = (
            f"{module_names[pin['distribution']]}/__init__.py"
            if pin["distribution"] in module_names
            else f"pkg{i}/code.py"
        )
        notice = f"pkg{i}/LICENSE"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, b"# original synthetic package\n")
            if pin["distribution"] == "spleeter":
                archive.writestr("spleeter/model/__init__.py", b"# original model fixture\n")
            archive.writestr(notice, b"original test notice")
        identity = capture_stream_input(path)
        pin.update(
            size_bytes=identity.size_bytes,
            sha256=identity.sha256,
            notices={notice: hashlib.sha256(b"original test notice").hexdigest()},
            omitted_members={},
            selected_members=None,
        )
    raw["source_correspondence"] = {
        "spleeter/__init__.py": hashlib.sha256(b"# original synthetic package\n").hexdigest()
    }
    for pin in raw["notices"]:
        path = artifacts / pin["filename"]
        path.write_bytes(b"original supplemental notice")
        identity = capture_stream_input(path)
        pin.update(size_bytes=identity.size_bytes, sha256=identity.sha256)
    model = artifacts / raw["model"]["filename"]
    with tarfile.open(model, "w:gz") as archive:
        for member in raw["model_members"]:
            payload = member["source_name"].encode()
            entry = tarfile.TarInfo(member["source_name"])
            entry.size = len(payload)
            archive.addfile(entry, io.BytesIO(payload))
            member.update(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    identity = capture_stream_input(model)
    raw["model"].update(size_bytes=identity.size_bytes, sha256=identity.sha256)
    pins = SpleeterPins.model_validate(raw)
    monkeypatch.setattr(backend, "load_spleeter_pins", lambda: pins)
    runtime = tmp_path / "trusted-python.bin"
    runtime.write_bytes(b"test runtime identity; never executed")
    adapter = tmp_path / "adapter.py"
    adapter.write_bytes(b"test adapter identity")
    monkeypatch.setattr(
        backend,
        "_runtime",
        lambda: (capture_stream_input(runtime), [capture_stream_input(runtime)]),
    )
    monkeypatch.setattr(backend, "model_adapters", lambda: [capture_stream_input(adapter)])
    return backend, artifacts, pins, runtime, adapter


def test_exclusive_prepare_reconstructs_all_members_and_preserves_inputs(recipe, tmp_path):
    backend, artifacts, pins, _, _ = recipe
    before = [capture_stream_input(path) for path in sorted(artifacts.iterdir())]
    record = backend.provision_spleeter(tmp_path / "backend", artifacts)
    assert backend.read_spleeter(record.root) == record
    assert len(record.artifacts) == 55 and record.model_qualification == "not_assessed"
    assert (record.root / "packages/model/source/appledouble-checkpoint.bin").read_bytes() == (
        b"./._checkpoint"
    )
    assert (record.root / "packages/model/model.index").read_bytes() == b"model.index"
    assert [capture_stream_input(path) for path in sorted(artifacts.iterdir())] == before
    with pytest.raises((ValueError, FileExistsError)):
        backend.provision_spleeter(record.root, artifacts)


@pytest.mark.parametrize("mutation", ["missing", "changed", "wrong-model-member"])
def test_invalid_artifacts_fail_before_creating_output(recipe, tmp_path, mutation):
    backend, artifacts, pins, _, _ = recipe
    if mutation == "missing":
        (artifacts / pins.artifacts[0].filename).unlink()
    elif mutation == "changed":
        (artifacts / pins.model.filename).write_bytes(b"not pinned model")
    else:
        pins.model_members[0].sha256 = "0" * 64
    output = tmp_path / "refused"
    with pytest.raises((ValueError, OSError, Suno2FLPError)):
        backend.provision_spleeter(output, artifacts)
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["extra", "changed", "forged-record", "runtime", "adapter"])
def test_current_runtime_payload_and_record_are_rechecked(recipe, tmp_path, mutation):
    backend, artifacts, _, runtime, adapter = recipe
    record = backend.provision_spleeter(tmp_path / "backend", artifacts)
    if mutation == "extra":
        (record.root / "packages/extra.py").write_bytes(b"extra")
    elif mutation == "changed":
        (record.root / "packages/model/model.index").write_bytes(b"changed")
    elif mutation == "runtime":
        runtime.write_bytes(b"changed trusted runtime")
    elif mutation == "adapter":
        adapter.write_bytes(b"changed adapter")
    else:
        data = json.loads((record.root / "backend.json").read_text())
        data["payload"].pop("model/model.index")
        (record.root / "backend.json").write_text(json.dumps(data))
    with pytest.raises((ValueError, Suno2FLPError)):
        backend.read_spleeter(record.root)


@pytest.mark.parametrize("destination", ["artifacts/inside", "site-packages/unsafe"])
def test_ambiguous_output_or_ambient_site_roots_are_refused(recipe, tmp_path, destination):
    backend, artifacts, _, _, _ = recipe
    output = tmp_path / destination
    output.parent.mkdir(exist_ok=True)
    with pytest.raises((ValueError, Suno2FLPError)):
        backend.provision_spleeter(output, artifacts)
    assert not output.exists()


def _native_protocol(record, pins, attempt):
    import struct

    from suno2flp.core.separation_probe import fixture_bytes
    from suno2flp.core.separation_runtime import PROBE_FRAMES, STEMS

    fixtures = []
    for fixture, frames in PROBE_FRAMES.items():
        source = fixture_bytes(fixture)
        assert (attempt / f"{fixture}.input.f32").read_bytes() == source
        hashes = {}
        for index, name in enumerate(STEMS):
            raw = b"".join(
                struct.pack("<f", value[0] * (index + 1) / 10)
                for value in struct.iter_unpack("<f", source)
            )
            for run in (1, 2):
                (attempt / f"{fixture}.{name}.{run}.f32").write_bytes(raw)
            hashes[name] = [hashlib.sha256(raw).hexdigest()] * 2
        fixtures.append(dict(fixture=fixture, frames=frames, hashes=hashes))
    data = {
        "profile": "spleeter4-native-probe-v1",
        "device_types": ["CPU"],
        "intra_op_threads": 8,
        "inter_op_threads": 1,
        "versions": {pin.distribution: pin.version for pin in pins.artifacts},
        "modules": {
            name: str(record.root / "packages" / name.replace(".", "/") / "__init__.py")
            for name in (
                "numpy",
                "tensorflow",
                "keras",
                "scipy",
                "pandas",
                "spleeter",
                "spleeter.model",
            )
        },
        "restored_variables": {"authored_fake": [1]},
        "restored_values_sha256": "a" * 64,
        "fixtures": fixtures,
        "repeatability_scope": "observed-two-runs-per-fixture",
        "tfio_loaded": False,
        "ambient_plugins_enabled": False,
    }
    (attempt / "result.json").write_text(json.dumps(data))


@pytest.mark.parametrize("mutation", [None, "payload", "output", "version", "external-module"])
def test_probe_rechecks_native_evidence_and_dependency_boundaries(
    recipe, tmp_path, monkeypatch, mutation
):
    backend, artifacts, pins, _, _ = recipe
    record = backend.provision_spleeter(tmp_path / "backend", artifacts)
    attempt = tmp_path / "probe"

    def process(argv, **kwargs):
        assert argv[1:4] == ["-I", "-S", "-B"]
        assert Path(argv[-1]) == attempt / "request.json"
        assert kwargs["timeout"] == 1800
        _native_protocol(record, pins, attempt)
        if mutation == "payload":
            (record.root / "packages/extra.py").write_bytes(b"injected")
        elif mutation == "output":
            (attempt / "impulses.bass.2.f32").write_bytes(b"truncated")
        elif mutation in ("version", "external-module"):
            data = json.loads((attempt / "result.json").read_text())
            if mutation == "version":
                data["versions"]["numpy"] = "0.0"
            else:
                data["modules"]["numpy"] = str(tmp_path / "ambient.py")
            (attempt / "result.json").write_text(json.dumps(data))
        return b"fake child protocol, not native qualification", b""

    monkeypatch.setattr(backend, "run_bounded_process", process)
    if mutation:
        with pytest.raises((ValueError, Suno2FLPError)):
            backend.verify_spleeter(record.root, attempt)
        assert not (attempt / "probe.json").exists()
    else:
        report = backend.verify_spleeter(record.root, attempt)
        assert len(report.evidence) == 3 and (attempt / "probe.json").is_file()
        assert report.model_qualification == "not_assessed" and not report.execution_allowed


def test_result_identity_must_describe_the_bytes_actually_parsed(recipe, tmp_path, monkeypatch):
    backend, artifacts, pins, _, _ = recipe
    record = backend.provision_spleeter(tmp_path / "backend", artifacts)
    attempt = tmp_path / "probe"

    def process(*args, **kwargs):
        _native_protocol(record, pins, attempt)
        return b"synthetic process", b""

    original = backend.load_unique_json

    def parse(raw):
        value = original(raw)
        if isinstance(value, dict) and value.get("profile") == "spleeter4-native-probe-v1":
            changed = {**value, "restored_values_sha256": "b" * 64}
            (attempt / "result.json").write_text(json.dumps(changed))
        return value

    monkeypatch.setattr(backend, "run_bounded_process", process)
    monkeypatch.setattr(backend, "load_unique_json", parse)
    with pytest.raises((ValueError, Suno2FLPError)):
        backend.verify_spleeter(record.root, attempt)
    assert not (attempt / "probe.json").exists()
