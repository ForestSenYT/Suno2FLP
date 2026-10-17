"""Exclusive offline wheel preparation and current fixed rhythm runtime checks."""

import hashlib
import platform
import sys
import sysconfig
import zipfile
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.beat_native import NativeBeatResult
from suno2flp.core.beat_runtime import BeatBackend, BeatPins
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_archives import ArchiveMember, archive_members
from suno2flp.integrations.basic_pitch_backend import check_artifact, new_model_directory
from suno2flp.integrations.codec_process import run_bounded_process

Cancel = Callable[[], bool] | None


def cancelled(callback: Cancel) -> None:
    if callback is not None and callback():
        raise DecodeCancelled()


def load_beat_pins() -> BeatPins:
    return BeatPins.model_validate(
        load_unique_json(Path(__file__).with_name("beat_pins.json").read_bytes())
    )


def _runtime() -> tuple[FileIdentity, list[FileIdentity]]:
    if (
        sys.platform != "win32"
        or sysconfig.get_platform() != "win-amd64"
        or platform.python_implementation() != "CPython"
        or platform.python_version() != "3.11.16"
    ):
        raise ValueError("Beat This! requires trusted application CPython3.11.16 Windows x64")
    executable = capture_stream_input(Path(sys.executable))
    prefix = Path(sys.base_prefix)
    return executable, [
        capture_stream_input(p)
        for p in sorted({executable.path, prefix / "python.exe", prefix / "python311.dll"})
    ]


def beat_adapters() -> list[FileIdentity]:
    here = Path(__file__)
    return [
        capture_stream_input(p)
        for p in (
            here,
            here.with_name("beat_worker.py"),
            here.with_name("beat_pins.json"),
            here.with_name("basic_pitch_archives.py"),
            here.with_name("basic_pitch_backend.py"),
            here.with_name("codec_process.py"),
            here.with_name("process_metrics.py"),
            here.parent.parent / "core/beat_runtime.py",
            here.parent.parent / "core/beat_native.py",
            here.parent.parent / "core/file_tree.py",
            here.parent.parent / "core/offline_files.py",
            here.parent.parent / "core/report_publication.py",
        )
    ]


def _copy_member(
    stream: object, target: Path, member: ArchiveMember, should_cancel: Cancel
) -> None:
    # Caller supplies a regular archive/file reader, not an extraction hook.
    from typing import BinaryIO, cast

    reader = cast(BinaryIO, stream)
    target = guarded_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    size, digest = 0, hashlib.sha256()
    with target.open("xb") as output:
        while block := reader.read(1024**2):
            cancelled(should_cancel)
            size += len(block)
            if size > member.size_bytes:
                raise ValueError("Artifact changed during installation")
            digest.update(block)
            output.write(block)
    if size != member.size_bytes or digest.hexdigest() != member.sha256:
        raise ValueError("Artifact changed during installation")


def _payload(
    pins: BeatPins,
    artifacts: list[FileIdentity],
    destination: Path | None = None,
    should_cancel: Cancel = None,
) -> dict[str, str]:
    if len(artifacts) != 20:
        raise ValueError("Beat backend requires all19 wheels and the fixed local checkpoint")
    result: dict[str, str] = {}
    seen: set[str] = set()
    for pin, identity in zip([*pins.artifacts, pins.model], artifacts, strict=True):
        cancelled(should_cancel)
        check_artifact(identity, pin)
        if identity.path.name != pin.filename:
            raise ValueError("Artifact filename differs from the fixed recipe")
        if pin == pins.model:
            members = {"models/final0.ckpt": ArchiveMember("", pin.size_bytes, pin.sha256)}
        else:
            members = archive_members(
                identity.path, omitted_members=pin.omitted_members, max_member_bytes=512 * 1024**2
            )
            expected = {**pin.notices}
            if pin.distribution == "beat-this":
                expected.update(pins.source_correspondence)
            if any(n not in members or members[n].sha256 != h for n, h in expected.items()):
                raise ValueError("Dependency notice or audited upstream source changed")
        for name, member in members.items():
            if name.casefold() in seen:
                raise ValueError("Dependency archives have colliding members")
            seen.add(name.casefold())
            result[name] = member.sha256
        if destination is not None:
            if pin == pins.model:
                with identity.path.open("rb") as stream:
                    _copy_member(
                        stream,
                        destination / "models/final0.ckpt",
                        members["models/final0.ckpt"],
                        should_cancel,
                    )
            else:
                with zipfile.ZipFile(identity.path) as archive:
                    for name, member in members.items():
                        with archive.open(member.source_name) as stream:
                            _copy_member(stream, destination / name, member, should_cancel)
    return result


def _verify_payload(record: BeatBackend, should_cancel: Cancel = None) -> None:
    cancelled(should_cancel)
    verify_inputs([record.python, *record.runtime, *record.artifacts, *record.adapters])
    root = guarded_path(record.root / "packages")
    current = {
        f.path.relative_to(root).as_posix(): f.sha256
        for f in capture_file_tree(root, should_cancel=should_cancel)
    }
    if current != record.payload:
        raise ValueError("Beat payload membership or bytes changed")
    cancelled(should_cancel)


def provision_beat_backend(
    output: Path, artifacts: Path, *, should_cancel: Cancel = None
) -> BeatBackend:
    if guarded_path(output).exists():
        raise FileExistsError("Backend output already exists")
    cancelled(should_cancel)
    python, runtime = _runtime()
    pins = load_beat_pins()
    inputs = [capture_stream_input(artifacts / p.filename) for p in [*pins.artifacts, pins.model]]
    adapters = beat_adapters()
    expected = _payload(pins, inputs, should_cancel=should_cancel)
    root = new_model_directory(output, [artifacts, *[a.path for a in [*runtime, *adapters]]])
    packages = root / "packages"
    packages.mkdir()
    actual = _payload(pins, inputs, packages, should_cancel)
    if actual != expected:
        raise ValueError("Beat artifact recipe changed during preparation")
    record = BeatBackend(
        root=root,
        python=python,
        runtime=runtime,
        artifacts=inputs,
        adapters=adapters,
        payload=actual,
    )
    publish_verified_report(
        root / "backend.json",
        record.model_dump_json(indent=2),
        [a.path for a in inputs],
        lambda: _verify_payload(record, should_cancel),
    )
    return record


def read_beat_backend(root: Path, *, should_cancel: Cancel = None) -> BeatBackend:
    cancelled(should_cancel)
    root = guarded_path(root)
    path = guarded_path(root / "backend.json")
    if path.stat().st_size > 4 * 1024**2:
        raise ValueError("Beat backend manifest exceeds budget")
    record = BeatBackend.model_validate(load_unique_json(path.read_bytes()))
    python, runtime = _runtime()
    if (record.root, record.python, record.runtime, record.adapters) != (
        root,
        python,
        runtime,
        beat_adapters(),
    ):
        raise ValueError("Beat backend runtime or current adapter recipe changed")
    if record.payload != _payload(load_beat_pins(), record.artifacts, should_cancel=should_cancel):
        raise ValueError("Beat backend payload differs from fixed artifacts")
    _verify_payload(record, should_cancel)
    return record


def call_beat_backend(
    record: BeatBackend,
    attempt: Path,
    pcm: FileIdentity,
    frames: int,
    sample_rate: int,
    channels: int,
    *,
    should_cancel: Cancel = None,
) -> NativeBeatResult:
    import json

    record = BeatBackend.model_validate(record.model_dump())
    if record != read_beat_backend(record.root, should_cancel=should_cancel):
        raise ValueError("Beat backend changed before inference")
    verify_inputs([pcm])
    attempt = guarded_path(attempt)
    if not attempt.is_dir() or list(attempt.iterdir()):
        raise ValueError("Native beat attempt must be an empty exclusive directory")
    request = dict(
        packages=str(record.root / "packages"),
        pins=str(Path(__file__).with_name("beat_pins.json")),
        pcm=str(pcm.path),
        frames=frames,
        sample_rate=sample_rate,
        channels=channels,
    )
    with (attempt / "request.json").open("x", encoding="utf-8") as stream:
        json.dump(request, stream, allow_nan=False)
    worker = Path(__file__).with_name("beat_worker.py")
    try:
        stdout, stderr = run_bounded_process(
            [str(record.python.path), "-I", "-S", "-B", str(worker), str(attempt / "request.json")],
            timeout=1800,
            should_cancel=should_cancel,
        )
    except Exception as error:
        for name in ("stdout", "stderr"):
            with (attempt / f"{name}.bin").open("xb") as log:
                log.write(getattr(error, name, b""))
        raise
    for name, raw in (("stdout", stdout), ("stderr", stderr)):
        with (attempt / f"{name}.bin").open("xb") as log:
            log.write(raw)
    verify_inputs([pcm])
    if record != read_beat_backend(record.root, should_cancel=should_cancel):
        raise ValueError("Beat backend changed during inference")
    path = guarded_path(attempt / "result.json")
    if path.stat().st_size > 1024**2:
        raise ValueError("Native beat result exceeds budget")
    result = NativeBeatResult.model_validate(load_unique_json(path.read_bytes()))
    if (result.frames, result.sample_rate, result.channels) != (frames, sample_rate, channels):
        raise ValueError("Native beat source geometry changed")
    pins = load_beat_pins()
    execution = result.execution
    if (execution.model_state_sha256, execution.geometry, execution.versions) != (
        pins.model_state_sha256,
        pins.model_geometry,
        {p.distribution: p.version for p in pins.artifacts},
    ):
        raise ValueError("Native beat execution differs from the audited recipe")
    expected_modules = {
        "torch",
        "torchaudio",
        "numpy",
        "soxr",
        "beat_this",
        "einops",
        "rotary_embedding_torch",
    }
    if set(execution.modules) != expected_modules or any(
        not guarded_path(p).is_relative_to(record.root / "packages")
        for p in execution.modules.values()
    ):
        raise ValueError("Native beat imports escaped the fixed private payload")
    return result
