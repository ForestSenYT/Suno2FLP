"""Explicit fixed-artifact preparation and current private ONNX runtime verification."""

import platform
import shutil
import sys
import sysconfig
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.transcription import (
    BasicPitchBackend,
    BasicPitchPins,
    BasicPitchProbe,
    ModelArtifactPin,
    SupplementalNotice,
)
from suno2flp.integrations.basic_pitch_archives import archive_members, install_members
from suno2flp.integrations.codec_process import run_bounded_process


def load_basic_pitch_pins() -> BasicPitchPins:
    return BasicPitchPins.model_validate(
        load_unique_json(Path(__file__).with_name("basic_pitch_pins.json").read_bytes())
    )


def check_artifact(identity: FileIdentity, pin: ModelArtifactPin | SupplementalNotice) -> None:
    if identity.size_bytes != pin.size_bytes or identity.sha256 != pin.sha256:
        raise ValueError(f"Fixed artifact size/hash mismatch: {pin.filename}")


def _runtime() -> tuple[FileIdentity, list[FileIdentity]]:
    if (
        sys.platform != "win32"
        or sysconfig.get_platform() != "win-amd64"
        or platform.python_implementation() != "CPython"
        or platform.python_version() != "3.11.16"
    ):
        raise ValueError("Basic Pitch requires trusted application CPython3.11.16 Windows x64")
    executable = capture_stream_input(Path(sys.executable))
    prefix = Path(sys.base_prefix)
    paths = {executable.path, prefix / "python.exe", prefix / "python311.dll"}
    return executable, [capture_stream_input(path) for path in sorted(paths)]


def model_adapters() -> list[FileIdentity]:
    here = Path(__file__)
    paths = [
        here,
        here.with_name("basic_pitch_archives.py"),
        here.with_name("basic_pitch_worker.py"),
        here.with_name("basic_pitch_pins.json"),
        here.with_name("codec_process.py"),
        here.parent.parent / "core/transcription.py",
        here.parent.parent / "core/transcription_clock.py",
        here.parent.parent / "core/file_tree.py",
    ]
    return [capture_stream_input(path) for path in paths]


def new_model_directory(output: Path, protected: list[Path]) -> Path:
    target = guarded_path(output)
    if target.exists() or not target.parent.is_dir():
        raise ValueError("Use a new directory with an existing parent")
    for path in protected:
        path = guarded_path(path)
        if target == path or target.is_relative_to(path) or path.is_relative_to(target):
            raise ValueError("Output overlaps protected inputs or model payload")
    if any((parent / "backend.json").exists() for parent in target.parents):
        raise ValueError("Output cannot be inside a backend")
    target.mkdir(exist_ok=False)
    return target


def _payload(
    pins: BasicPitchPins, artifacts: list[FileIdentity], destination: Path | None = None
) -> dict[str, str]:
    if len(artifacts) != len(pins.artifacts) + 1:
        raise ValueError("Backend needs the complete fixed artifact inventory")
    result: dict[str, str] = {}
    seen: set[str] = set()
    for pin, identity in zip(pins.artifacts, artifacts[:-1], strict=True):
        check_artifact(identity, pin)
        if identity.path.name != pin.filename:
            raise ValueError("Artifact filename differs from the fixed recipe")
        members = archive_members(
            identity.path,
            source_inventory=pin.source_inventory,
            omitted_members=pin.omitted_members,
        )
        for name, expected in pin.notices.items():
            if name not in members or members[name].sha256 != expected:
                raise ValueError("Required dependency notice changed or is missing")
        if pin.distribution == "basic-pitch":
            for name, expected in pins.source_correspondence.items():
                if name not in members or members[name].sha256 != expected:
                    raise ValueError("Basic Pitch wheel differs from the audited source/model")
        if pin.selected_members is not None:
            members = {target: members[name] for name, target in pin.selected_members.items()}
        for name, member in members.items():
            if name.casefold() in seen:
                raise ValueError("Dependency archives have colliding members")
            seen.add(name.casefold())
            result[name] = member.sha256
        if destination is not None:
            install_members(identity.path, destination, members)
    notice, identity = pins.supplemental_notice, artifacts[-1]
    check_artifact(identity, notice)
    if identity.path.name != notice.filename or notice.target.casefold() in seen:
        raise ValueError("Supplemental notice inventory is inconsistent")
    result[notice.target] = notice.sha256
    if destination is not None:
        target = guarded_path(destination / notice.target)
        target.parent.mkdir(exist_ok=True)
        with identity.path.open("rb") as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
    if sum(identity.size_bytes for identity in artifacts) > 256 * 1024**2:
        raise ValueError("Model artifact recipe exceeds its budget")
    return result


def provision_basic_pitch(output: Path, artifact_directory: Path) -> BasicPitchBackend:
    # Missing prerequisites fail before creating output; downloads are separate and explicit.
    if guarded_path(output).exists():
        raise FileExistsError("Backend output already exists")
    python, runtime = _runtime()
    pins = load_basic_pitch_pins()
    artifact_pins: list[ModelArtifactPin | SupplementalNotice] = [
        *pins.artifacts,
        pins.supplemental_notice,
    ]
    artifacts = [capture_stream_input(artifact_directory / pin.filename) for pin in artifact_pins]
    adapters = model_adapters()
    expected = _payload(pins, artifacts)
    root = new_model_directory(output, [artifact_directory, *[a.path for a in adapters]])
    packages = root / "packages"
    packages.mkdir()
    payload = _payload(pins, artifacts, packages)
    if payload != expected:
        raise ValueError("Artifact payload changed during preparation")
    record = BasicPitchBackend(
        root=root,
        python=python,
        runtime=runtime,
        artifacts=artifacts,
        adapters=adapters,
        payload=payload,
    )
    _verify_payload(record)
    with (root / "backend.json").open("x", encoding="utf-8") as stream:
        stream.write(record.model_dump_json(indent=2))
    read_basic_pitch(root)
    return record


def _verify_payload(record: BasicPitchBackend) -> None:
    verify_inputs([record.python, *record.runtime, *record.artifacts, *record.adapters])
    root = guarded_path(record.root / "packages")
    actual = {
        identity.path.relative_to(root).as_posix(): identity.sha256
        for identity in capture_file_tree(root)
    }
    if actual != record.payload:
        raise ValueError("Model payload membership or bytes changed")


def read_basic_pitch(root: Path) -> BasicPitchBackend:
    root = guarded_path(root)
    path = guarded_path(root / "backend.json")
    if path.stat().st_size > 4 * 1024**2:
        raise ValueError("Model backend record exceeds budget")
    record = BasicPitchBackend.model_validate(load_unique_json(path.read_bytes()))
    python, runtime = _runtime()
    if (record.root, record.python, record.runtime, record.adapters) != (
        root,
        python,
        runtime,
        model_adapters(),
    ):
        raise ValueError("Backend runtime or current adapter recipe changed")
    if record.payload != _payload(load_basic_pitch_pins(), record.artifacts):
        raise ValueError("Backend payload differs from fixed artifacts")
    _verify_payload(record)
    return record


def call_basic_pitch(
    record: BasicPitchBackend,
    attempt: Path,
    request: dict[str, object],
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[bytes, bytes]:
    record = BasicPitchBackend.model_validate(record.model_dump())
    if record != read_basic_pitch(record.root):
        raise ValueError("Backend changed before inference")
    import json

    request = {**request, "packages": str(record.root / "packages")}
    request_path = attempt / "request.json"
    with request_path.open("x", encoding="utf-8") as stream:
        json.dump(request, stream, allow_nan=False)
    worker = Path(__file__).with_name("basic_pitch_worker.py")
    try:
        stdout, stderr = run_bounded_process(
            [str(record.python.path), "-I", "-S", "-B", str(worker), str(request_path)],
            should_cancel=should_cancel,
            timeout=1800,
        )
    except Exception as error:
        for name in ("stdout", "stderr"):
            with (attempt / f"{name}.bin").open("xb") as stream:
                stream.write(getattr(error, name, b""))
        raise
    for name, raw in (("stdout", stdout), ("stderr", stderr)):
        with (attempt / f"{name}.bin").open("xb") as stream:
            stream.write(raw)
    if record != read_basic_pitch(record.root):
        raise ValueError("Backend changed during inference")
    return stdout, stderr


def verify_basic_pitch(
    root: Path, probe_directory: Path, *, should_cancel: Callable[[], bool] | None = None
) -> BasicPitchBackend:
    record = read_basic_pitch(root)
    attempt = new_model_directory(probe_directory, [root, *[a.path for a in record.artifacts]])
    call_basic_pitch(record, attempt, {"operation": "probe"}, should_cancel=should_cancel)
    path = attempt / "result.json"
    if path.stat().st_size > 1024**2:
        raise ValueError("Native handshake exceeds budget")
    probe = BasicPitchProbe.model_validate(load_unique_json(path.read_bytes()))
    validate_basic_pitch_probe(probe, root)
    return record


def validate_basic_pitch_probe(probe: BasicPitchProbe, root: Path) -> None:
    probe = BasicPitchProbe.model_validate(probe.model_dump())
    expected_shapes = {"note": [1, 172, 88], "onset": [1, 172, 88], "contour": [1, 172, 264]}
    expected_versions = {
        "onnxruntime": "1.23.2",
        "numpy": "2.3.5",
        "scipy": "1.16.3",
        "basic-pitch": "0.4.0",
    }
    if probe.shapes != expected_shapes or probe.versions != expected_versions:
        raise ValueError("Native shapes/versions differ from the fixed profile")
    payload = guarded_path(root / "packages")
    expected_modules = {
        "numpy",
        "onnxruntime",
        "scipy",
        "basic_pitch",
        "librosa",
        "pretty_midi",
        "mir_eval",
        "resampy",
    }
    if set(probe.modules) != expected_modules or any(
        not guarded_path(path).is_relative_to(payload) for path in probe.modules.values()
    ):
        raise ValueError("Native packages loaded outside their isolated payload")
