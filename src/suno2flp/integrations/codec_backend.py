"""Exclusive fixed-wheel audio runtime preparation, current integrity and real handshake."""

import hashlib
import os
import platform
import stat
import sys
import sysconfig
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from suno2flp.core.audio_input import AudioPreflightError
from suno2flp.core.codec_backend import (
    CodecAudioResult,
    CodecBackendRecord,
    CodecPins,
    CodecPlatformPin,
    CodecProbe,
    CodecProcessError,
    CodecWheelPin,
)
from suno2flp.core.offline_files import (
    capture_input,
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.integrations.codec_process import run_bounded_process


def _error(code: str, message: str) -> AudioPreflightError:
    return AudioPreflightError(code, message, blocked=True)


def load_codec_pins() -> CodecPins:
    path = Path(__file__).with_name("codec_wheels.json")
    return CodecPins.model_validate(load_unique_json(path.read_bytes()))


def codec_platform() -> Literal["windows-x86_64", "linux-x86_64"]:
    if sysconfig.get_platform() not in ("win-amd64", "linux-x86_64") or sys.platform not in (
        "win32",
        "linux",
    ):
        raise _error("audio_backend_unavailable", "Only Windows/Linux x86_64 is qualified")
    if sys.platform == "linux":
        name, version = platform.libc_ver()
        if name != "glibc" or tuple(int(v) for v in version.split(".")[:2]) < (2, 28):
            raise _error("audio_backend_unavailable", "The pinned Linux wheel requires glibc2.28+")
    return "windows-x86_64" if sys.platform == "win32" else "linux-x86_64"


def codec_abi() -> Literal["cp311", "cp314"]:
    abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    if (
        platform.python_implementation() != "CPython"
        or load_codec_pins().python_versions.get(abi) != platform.python_version()
    ):
        raise _error(
            "audio_python_unavailable", "Use the pinned application Python3.11.16 or3.14.7"
        )
    return "cp311" if abi == "cp311" else "cp314"


def _adapters() -> list[FileIdentity]:
    here = Path(__file__).resolve()
    paths = [
        here,
        here.with_name("codec_worker.py"),
        here.with_name("codec_process.py"),
        here.with_name("codec_wheels.json"),
        here.parent.parent / "core/codec_backend.py",
    ]
    return [capture_stream_input(path) for path in paths]


def _python(python: Path) -> tuple[FileIdentity, list[FileIdentity]]:
    # A record may never choose an executable: reuse the already trusted application runtime.
    current = Path(sys.executable).resolve()
    if python.resolve() != current:
        raise _error("audio_python_unavailable", "Backend records cannot select another executable")
    codec_abi()
    executable = capture_stream_input(current)
    prefix = Path(sys.base_prefix)
    dll = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
    paths = [
        current,
        prefix / "python.exe",
        prefix / dll,
        prefix / "lib" / (sysconfig.get_config_var("LDLIBRARY") or "missing"),
    ]
    identities = [
        capture_stream_input(path) for path in sorted({p.resolve() for p in paths if p.is_file()})
    ]
    if not identities:
        raise _error("audio_python_unavailable", "Python runtime files could not be identified")
    return executable, identities


def _archive(identity: FileIdentity, pin: CodecWheelPin) -> None:
    if identity.size_bytes != pin.size_bytes or identity.sha256 != pin.sha256:
        raise _error(
            "audio_wheel_integrity_failed", f"Fixed wheel size/hash mismatch: {pin.filename}"
        )


def _members(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    seen: set[str] = set()
    expanded = 0
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            name = entry.filename.rstrip("/")
            parts = name.split("/")
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if (
                not parts
                or any(part in ("", ".", "..") or "\\" in part or ":" in part for part in parts)
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
            ):
                raise _error(
                    "audio_wheel_integrity_failed", "Ambiguous, linked or special wheel entry"
                )
            if entry.is_dir():
                continue
            expanded += entry.file_size
            if (
                entry.file_size > 64 * 1024**2
                or expanded > 512 * 1024**2
                or name.casefold() in seen
            ):
                raise _error(
                    "audio_wheel_integrity_failed",
                    "Wheel expansion/duplicate entry exceeds profile",
                )
            seen.add(name.casefold())
            result[name] = hashlib.sha256(archive.read(entry)).hexdigest()
    return result


def _payload(root: Path, profile: CodecPlatformPin) -> tuple[dict[str, str], list[FileIdentity]]:
    expected: dict[str, str] = {}
    for pin in profile.wheels:
        current = _members(root / "wheels" / pin.filename)
        if {p.casefold() for p in current} & {p.casefold() for p in expected}:
            raise _error("audio_wheel_integrity_failed", "Colliding fixed wheel entries")
        expected.update(current)
    packages = guarded_path(root / "packages")
    actual = set()
    for path in packages.rglob("*"):
        guarded_path(path)
        if path.is_file():
            actual.add(path.relative_to(packages).as_posix())
    if actual != set(expected):
        raise _error(
            "audio_backend_integrity_failed",
            "Installed payload inventory differs from fixed wheels",
        )
    identities = []
    for name, digest in expected.items():
        identity = capture_stream_input(packages / name)
        if identity.sha256 != digest:
            raise _error("audio_backend_integrity_failed", f"Installed payload changed: {name}")
        identities.append(identity)
    return expected, identities


def _probe(root: Path, python: FileIdentity, profile: CodecPlatformPin) -> CodecProbe:
    raw, stderr = run_bounded_process(
        [
            str(python.path),
            "-I",
            "-S",
            "-B",
            str(Path(__file__).with_name("codec_worker.py").resolve()),
            "probe",
            str(root / "packages"),
        ],
        timeout=30,
    )
    if stderr:
        raise _error(
            "audio_backend_unavailable", "Native handshake emitted unqualified diagnostics"
        )
    probe = CodecProbe.model_validate(load_unique_json(raw))
    expected_versions = {w.distribution: w.version for w in profile.wheels}
    if (
        probe.platform != codec_platform()
        or probe.python_abi != codec_abi()
        or probe.python_version != platform.python_version()
        or probe.versions != expected_versions
        or probe.native_path != root / "packages/_soundfile_data" / profile.native_filename
        or probe.native_sha256 != profile.native_sha256
        or not {"WAV", "FLAC", "MP3"}.issubset(probe.formats)
    ):
        raise _error(
            "audio_backend_integrity_failed", "Actual native handshake disagrees with fixed runtime"
        )
    return probe


def _download(pin: CodecWheelPin, destination: Path) -> None:
    size = 0
    with urllib.request.urlopen(pin.url, timeout=30) as response, destination.open("xb") as output:
        while block := response.read(1024**2):
            size += len(block)
            if size > pin.size_bytes:
                raise _error("audio_wheel_integrity_failed", "Download exceeds fixed wheel length")
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
    _archive(capture_stream_input(destination), pin)


def provision_codec_backend(
    directory: Path, python: Path, *, wheelhouse: Path | None = None
) -> CodecBackendRecord:
    root = guarded_path(directory)
    if (
        root.exists()
        or not root.parent.is_dir()
        or any((p / "backend.json").exists() for p in root.parents)
    ):
        raise _error("audio_backend_output_unsafe", "Use a new directory outside existing backends")
    profile_name = codec_platform()
    abi = codec_abi()
    profile = load_codec_pins().platforms[f"{profile_name}-{abi}"]
    sources = []
    if wheelhouse is not None:
        wheelhouse = guarded_path(wheelhouse)
        if not wheelhouse.is_dir():
            raise _error("audio_wheel_missing", "The explicit offline wheelhouse is unavailable")
        for pin in profile.wheels:
            try:
                identity = capture_stream_input(wheelhouse / pin.filename)
            except OSError as error:
                raise _error(
                    "audio_wheel_missing", f"Missing fixed offline wheel: {pin.filename}"
                ) from error
            _archive(identity, pin)
            sources.append(identity)
    executable, python_runtime = _python(python)
    root.mkdir()
    (root / "wheels").mkdir()
    for index, pin in enumerate(profile.wheels):
        destination = root / "wheels" / pin.filename
        if wheelhouse is None:
            _download(pin, destination)
        else:
            with sources[index].path.open("rb") as original, destination.open("xb") as output:
                while block := original.read(1024**2):
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
            _archive(capture_stream_input(destination), pin)
    verify_inputs(sources)
    packages = root / "packages"
    packages.mkdir()
    for pin in profile.wheels:
        archive_path = root / "wheels" / pin.filename
        _members(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                target = guarded_path(packages / entry.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output, archive.open(entry) as original:
                    while block := original.read(1024**2):
                        output.write(block)
    payload, payload_inputs = _payload(root, profile)
    adapters = _adapters()
    probe = _probe(root, executable, profile)
    verify_inputs([executable, *python_runtime, *payload_inputs, *adapters])
    wheels = [capture_stream_input(root / "wheels" / pin.filename) for pin in profile.wheels]
    record = CodecBackendRecord(
        root=root,
        platform=profile_name,
        python=executable,
        python_abi=abi,
        python_runtime=python_runtime,
        wheels=wheels,
        adapter_files=adapters,
        payload=payload,
        probe=probe,
    )
    with (root / "backend.json").open("xb") as stream:
        stream.write((record.model_dump_json(indent=2) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return verify_codec_backend(root)


def verify_codec_backend(directory: Path) -> CodecBackendRecord:
    root = guarded_path(directory)
    manifest = root / "backend.json"
    try:
        if manifest.stat().st_size > 2 * 1024**2:
            raise ValueError("Backend record exceeds profile")
        identity, raw = capture_input(manifest)
        record = CodecBackendRecord.model_validate(load_unique_json(raw))
    except (OSError, ValueError) as error:
        raise _error(
            "audio_backend_unavailable", f"Missing/invalid isolated audio backend: {error}"
        ) from error
    name = codec_platform()
    abi = codec_abi()
    profile = load_codec_pins().platforms[f"{name}-{abi}"]
    if (
        record.root != root
        or record.platform != name
        or record.python_abi != abi
        or record.adapter_files != _adapters()
    ):
        raise _error(
            "audio_backend_integrity_failed", "Backend location/profile/adapter recipe changed"
        )
    current_python, current_runtime = _python(record.python.path)
    if record.python != current_python or record.python_runtime != current_runtime:
        raise _error("audio_backend_integrity_failed", "Trusted application Python runtime changed")
    if len(record.wheels) != len(profile.wheels):
        raise _error("audio_backend_integrity_failed", "Incomplete fixed wheel identities")
    verify_inputs([record.python, *record.python_runtime, *record.wheels, *record.adapter_files])
    for wheel, pin in zip(record.wheels, profile.wheels, strict=True):
        if wheel.path != root / "wheels" / pin.filename:
            raise _error(
                "audio_backend_integrity_failed", "Wheel location differs from fixed profile"
            )
        _archive(wheel, pin)
    payload, inputs = _payload(root, profile)
    if record.payload != payload or record.probe != _probe(root, record.python, profile):
        raise _error(
            "audio_backend_integrity_failed", "Current payload/handshake differs from record"
        )
    verify_inputs(
        [
            identity,
            record.python,
            *record.python_runtime,
            *record.wheels,
            *record.adapter_files,
            *inputs,
        ]
    )
    return record


def run_codec_worker(
    backend: Path,
    mode: Literal["decode", "verify"],
    arguments: list[str],
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> CodecAudioResult:
    if mode not in ("decode", "verify"):
        raise ValueError("Only fixed audio worker modes are accepted")
    record = verify_codec_backend(backend)
    raw, stderr = run_bounded_process(
        [
            str(record.python.path),
            "-I",
            "-S",
            "-B",
            str(Path(__file__).with_name("codec_worker.py").resolve()),
            mode,
            str(record.root / "packages"),
            *arguments,
        ],
        should_cancel=should_cancel,
    )
    if stderr:
        raise CodecProcessError(
            "audio_worker_diagnostic",
            "Native codec emitted unqualified diagnostics",
            stdout=raw,
            stderr=stderr,
        )
    result = CodecAudioResult.model_validate(load_unique_json(raw))
    if result.mode != mode or result.runtime != record.probe:
        raise _error(
            "audio_backend_integrity_failed",
            "Audio worker runtime/protocol disagrees with handshake",
        )
    verify_codec_backend(backend)
    return result
