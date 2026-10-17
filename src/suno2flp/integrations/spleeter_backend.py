"""Explicit fixed local graph preparation; no downloads or model imports in core."""

import hashlib
import json
import platform
import shutil
import sys
import sysconfig
import tarfile
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import (
    capture_input,
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.separation_probe import check_fixture, fixture_bytes
from suno2flp.core.separation_runtime import (
    PROBE_FRAMES,
    NativeSeparationProbe,
    SeparationArtifactPin,
    SpleeterBackend,
    SpleeterPins,
    SpleeterProbe,
)
from suno2flp.core.transcription import SupplementalNotice
from suno2flp.integrations.basic_pitch_archives import (
    ArchiveMember,
    archive_members,
    install_members,
)
from suno2flp.integrations.basic_pitch_backend import check_artifact, new_model_directory
from suno2flp.integrations.codec_process import run_bounded_process


def load_spleeter_pins() -> SpleeterPins:
    return SpleeterPins.model_validate(
        load_unique_json(Path(__file__).with_name("spleeter_pins.json").read_bytes())
    )


def _runtime() -> tuple[FileIdentity, list[FileIdentity]]:
    if (
        sys.platform != "win32"
        or sysconfig.get_platform() != "win-amd64"
        or platform.python_implementation() != "CPython"
        or platform.python_version() != "3.11.16"
    ):
        raise ValueError("Spleeter requires trusted application CPython3.11.16 Windows x64")
    executable = capture_stream_input(Path(sys.executable))
    prefix = Path(sys.base_prefix)
    paths = {executable.path, prefix / "python.exe", prefix / "python311.dll"}
    return executable, [capture_stream_input(path) for path in sorted(paths)]


def model_adapters() -> list[FileIdentity]:
    here = Path(__file__)
    files = [
        here,
        here.with_name("spleeter_worker.py"),
        here.with_name("spleeter_pins.json"),
        here.with_name("basic_pitch_archives.py"),
        here.with_name("basic_pitch_backend.py"),
        here.with_name("codec_process.py"),
        here.parent.parent / "core/separation_runtime.py",
        here.parent.parent / "core/separation_probe.py",
        here.parent.parent / "core/file_tree.py",
        here.parent.parent / "core/offline_files.py",
        here.parent.parent / "core/models.py",
        here.parent.parent / "core/offline_models.py",
        here.parent.parent / "core/transcription.py",
    ]
    return [capture_stream_input(path) for path in files]


def _private_root(path: Path) -> Path:
    root = guarded_path(path)
    if any(name in str(root).casefold() for name in ("site-packages", "dist-packages")):
        raise ValueError("Use a private backend outside ambient site-packages")
    return root


def _model_members(path: Path, pins: SpleeterPins) -> dict[str, ArchiveMember]:
    # The official tar contains one ./._checkpoint AppleDouble member. Its exact
    # identity maps to an inert safe name, without relaxing generic archive paths.
    expected = {member.source_name: member for member in pins.model_members}
    if len(expected) != 5:
        raise ValueError("Model member recipe is incomplete")
    result: dict[str, ArchiveMember] = {}
    with tarfile.open(path, "r:gz") as archive:
        entries = archive.getmembers()
        if len(entries) != len(expected):
            raise ValueError("Model archive membership changed")
        seen: set[str] = set()
        for entry in entries:
            if entry.name not in expected or entry.name in seen or not entry.isfile():
                raise ValueError("Model archive needs exact unique regular members")
            seen.add(entry.name)
            pin = expected[entry.name]
            if entry.size != pin.size_bytes:
                raise ValueError("Model member size changed")
            stream = archive.extractfile(entry)
            assert stream is not None
            with stream:
                hasher = hashlib.sha256()
                while block := stream.read(1024**2):
                    hasher.update(block)
                digest = hasher.hexdigest()
            if digest != pin.sha256:
                raise ValueError("Model member hash changed")
            result[pin.target] = ArchiveMember(entry.name, entry.size, digest)
    if len(result) != len(expected):
        raise ValueError("Model target membership is ambiguous")
    return result


def _payload(
    pins: SpleeterPins, artifacts: list[FileIdentity], destination: Path | None = None
) -> dict[str, str]:
    all_pins: list[SeparationArtifactPin | SupplementalNotice] = [
        *pins.artifacts,
        pins.model,
        *pins.notices,
    ]
    if len(artifacts) != len(all_pins):
        raise ValueError("Backend needs the complete fixed artifact inventory")
    if sum(identity.size_bytes for identity in artifacts) > 768 * 1024**2:
        raise ValueError("Separation artifacts exceed the dedicated budget")
    for pin, identity in zip(all_pins, artifacts, strict=True):
        check_artifact(identity, pin)
        if identity.path.name != pin.filename:
            raise ValueError("Artifact filename differs from the fixed recipe")
    result: dict[str, str] = {}
    seen: set[str] = set()
    expanded = 0

    def add(members: dict[str, ArchiveMember]) -> None:
        nonlocal expanded
        for name, member in members.items():
            if name.casefold() in seen:
                raise ValueError("Separation payload has colliding members")
            seen.add(name.casefold())
            result[name] = member.sha256
            expanded += member.size_bytes
            if expanded > 3 * 1024**3 or len(seen) > 20_000:
                raise ValueError("Separation payload exceeds the dedicated budget")

    for pin, identity in zip(pins.artifacts, artifacts[: len(pins.artifacts)], strict=True):
        members = archive_members(
            identity.path,
            omitted_members=pin.omitted_members,
            max_member_bytes=1024**3,
            max_expanded=2 * 1024**3,
        )
        expected_members = dict(pin.notices)
        if pin.distribution == "spleeter":
            expected_members.update(pins.source_correspondence)
        if any(
            name not in members or members[name].sha256 != digest
            for name, digest in expected_members.items()
        ):
            raise ValueError("Required notice or corresponding source member changed")
        if pin.selected_members is not None:
            members = {target: members[name] for name, target in pin.selected_members.items()}
        add(members)
        if destination is not None:
            install_members(identity.path, destination, members)
    model_id = artifacts[len(pins.artifacts)]
    model_members = _model_members(model_id.path, pins)
    add(model_members)
    if destination is not None:
        install_members(model_id.path, destination, model_members)
    for notice, identity in zip(pins.notices, artifacts[-len(pins.notices) :], strict=True):
        add({notice.target: ArchiveMember(notice.filename, notice.size_bytes, notice.sha256)})
        if destination is not None:
            target = guarded_path(destination / notice.target)
            if not target.is_relative_to(destination):
                raise ValueError("Notice target escapes private output")
            target.parent.mkdir(parents=True, exist_ok=True)
            with identity.path.open("rb") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
    return result


def _verify_payload(record: SpleeterBackend) -> None:
    verify_inputs([record.python, *record.runtime, *record.artifacts, *record.adapters])
    root = _private_root(record.root / "packages")
    actual = {
        identity.path.relative_to(root).as_posix(): identity.sha256
        for identity in capture_file_tree(root, max_bytes=3 * 1024**3)
    }
    if actual != record.payload:
        raise ValueError("Separation payload membership or bytes changed")


def provision_spleeter(output: Path, artifact_directory: Path) -> SpleeterBackend:
    output = _private_root(output)
    if output.exists():
        raise FileExistsError("Backend output already exists")
    python, runtime = _runtime()
    pins = load_spleeter_pins()
    all_pins: list[SeparationArtifactPin | SupplementalNotice] = [
        *pins.artifacts,
        pins.model,
        *pins.notices,
    ]
    artifacts = [capture_stream_input(artifact_directory / pin.filename) for pin in all_pins]
    adapters = model_adapters()
    expected = _payload(pins, artifacts)
    root = new_model_directory(output, [artifact_directory, *[a.path for a in adapters]])
    packages = root / "packages"
    packages.mkdir()
    payload = _payload(pins, artifacts, packages)
    if payload != expected:
        raise ValueError("Separation artifacts changed during preparation")
    record = SpleeterBackend(
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
    read_spleeter(root)
    return record


def read_spleeter(root: Path) -> SpleeterBackend:
    root = _private_root(root)
    path = guarded_path(root / "backend.json")
    if path.stat().st_size > 8 * 1024**2:
        raise ValueError("Separation backend record exceeds budget")
    record = SpleeterBackend.model_validate(load_unique_json(path.read_bytes()))
    python, runtime = _runtime()
    if (record.root, record.python, record.runtime, record.adapters) != (
        root,
        python,
        runtime,
        model_adapters(),
    ):
        raise ValueError("Separation runtime or current adapter recipe changed")
    if record.payload != _payload(load_spleeter_pins(), record.artifacts):
        raise ValueError("Separation payload differs from fixed artifacts")
    _verify_payload(record)
    return record


def _validate_native(probe: NativeSeparationProbe, record: SpleeterBackend) -> None:
    expected_versions = {pin.distribution: pin.version for pin in load_spleeter_pins().artifacts}
    if probe.versions != expected_versions:
        raise ValueError("Native versions differ from the complete fixed recipe")
    names = ("numpy", "tensorflow", "keras", "scipy", "pandas", "spleeter", "spleeter.model")
    expected_modules = {
        name: record.root / "packages" / name.replace(".", "/") / "__init__.py" for name in names
    }
    if probe.modules != expected_modules:
        raise ValueError("Native modules differ from the fixed private payload")
    for path in probe.modules.values():
        identity = capture_stream_input(path)
        relative = identity.path.relative_to(record.root / "packages").as_posix()
        if record.payload.get(relative) != identity.sha256:
            raise ValueError("Native imported module bytes changed")


def verify_spleeter(
    root: Path, output: Path, *, should_cancel: Callable[[], bool] | None = None
) -> SpleeterProbe:
    record = read_spleeter(root)
    backend_identity = capture_stream_input(record.root / "backend.json")
    attempt = new_model_directory(output, [record.root, *[a.path.parent for a in record.artifacts]])
    for name in PROBE_FRAMES:
        with (attempt / f"{name}.input.f32").open("xb") as stream:
            stream.write(fixture_bytes(name))
    request = attempt / "request.json"
    with request.open("x", encoding="utf-8") as stream:
        json.dump({"operation": "probe", "packages": str(record.root / "packages")}, stream)
    request_identity = capture_stream_input(request)
    try:
        stdout, stderr = run_bounded_process(
            [
                str(record.python.path),
                "-I",
                "-S",
                "-B",
                str(Path(__file__).with_name("spleeter_worker.py")),
                str(request),
            ],
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
    if record != read_spleeter(root):
        raise ValueError("Separation backend changed during native probe")
    path = guarded_path(attempt / "result.json")
    if path.stat().st_size > 2 * 1024**2:
        raise ValueError("Native handshake exceeds budget")
    result_identity, result_bytes = capture_input(path)
    native = NativeSeparationProbe.model_validate(load_unique_json(result_bytes))
    _validate_native(native, record)
    evidence = [check_fixture(attempt, result) for result in native.fixtures]
    report = SpleeterProbe(
        backend_record=backend_identity,
        backend=record,
        native=native,
        evidence=evidence,
        request=request_identity,
        result=result_identity,
        stdout=capture_stream_input(attempt / "stdout.bin"),
        stderr=capture_stream_input(attempt / "stderr.bin"),
    )
    witnesses = [report.backend_record, report.request, report.result, report.stdout, report.stderr]
    for item in report.evidence:
        witnesses.extend([item.source, *item.outputs, item.residual])
    verify_inputs(witnesses)
    _verify_payload(record)
    with (attempt / "probe.json").open("x", encoding="utf-8") as stream:
        stream.write(report.model_dump_json(indent=2))
    verify_inputs(witnesses)
    _verify_payload(record)
    return report
