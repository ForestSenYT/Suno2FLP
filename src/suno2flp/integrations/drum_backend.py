"""New isolated fixed encoder payloads; never call an upstream convenience loader."""

from pathlib import Path

from suno2flp.core.drum_clock import drum_output_rows
from suno2flp.core.drum_native import NativeDrumResult
from suno2flp.core.drum_runtime import DrumBackend, DrumPins
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.beat_backend import Cancel, _runtime, cancelled
from suno2flp.integrations.codec_process import run_bounded_process
from suno2flp.integrations.drum_source import drum_payload


def load_drum_pins() -> DrumPins:
    return DrumPins.model_validate(
        load_unique_json(Path(__file__).with_name("drum_pins.json").read_bytes())
    )


def drum_adapters() -> list[FileIdentity]:
    root = Path(__file__).resolve().parent.parent
    names = (
        "integrations/drum_backend.py",
        "integrations/drum_source.py",
        "integrations/drum_probe.py",
        "integrations/drum_worker.py",
        "integrations/drum_activations.py",
        "integrations/drum_pins.json",
        "integrations/beat_backend.py",
        "integrations/basic_pitch_archives.py",
        "integrations/basic_pitch_backend.py",
        "integrations/codec_process.py",
        "integrations/process_metrics.py",
        "core/drum_runtime.py",
        "core/drum_native.py",
        "core/drum_clock.py",
        "core/drum_scoring.py",
        "core/separation_clock.py",
        "core/models.py",
        "core/transcription.py",
        "core/note_scoring.py",
        "core/offline_models.py",
        "core/offline_files.py",
        "core/report_publication.py",
        "core/file_tree.py",
        "core/errors.py",
    )
    return [capture_stream_input(root / name) for name in names]


def verify_drum_payload(record: DrumBackend, should_cancel: Cancel = None) -> None:
    cancelled(should_cancel)
    verify_inputs([record.python, *record.runtime, *record.artifacts, *record.adapters])
    root = guarded_path(record.root / "packages")
    current = {
        i.path.relative_to(root).as_posix(): i.sha256
        for i in capture_file_tree(root, max_bytes=3 * 1024**3, should_cancel=should_cancel)
    }
    if current != record.payload:
        raise ValueError("Drum payload membership or bytes changed")
    cancelled(should_cancel)


def provision_drum_backend(
    output: Path, artifacts: Path, *, should_cancel: Cancel = None
) -> DrumBackend:
    if guarded_path(output).exists():
        raise FileExistsError("Drum backend output already exists")
    cancelled(should_cancel)
    python, runtime = _runtime()
    pins = load_drum_pins()
    filenames = [p.filename for p in [*pins.artifacts, pins.source]]
    filenames.extend(p.filename for p in pins.notices)
    inputs = [capture_stream_input(artifacts / name) for name in filenames]
    adapters = drum_adapters()
    expected = drum_payload(pins, inputs, should_cancel=should_cancel)
    root = new_model_directory(output, [artifacts, *[i.path for i in [*runtime, *adapters]]])
    packages = root / "packages"
    packages.mkdir()
    actual = drum_payload(pins, inputs, packages, should_cancel)
    if actual != expected:
        raise ValueError("Drum fixed payload recipe changed during preparation")
    record = DrumBackend(
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
        [i.path for i in inputs],
        lambda: verify_drum_payload(record, should_cancel),
    )
    return record


def read_drum_backend(root: Path, *, should_cancel: Cancel = None) -> DrumBackend:
    cancelled(should_cancel)
    root = guarded_path(root)
    path = guarded_path(root / "backend.json")
    if path.stat().st_size > 4 * 1024**2:
        raise ValueError("Drum backend manifest exceeds budget")
    record = DrumBackend.model_validate(load_unique_json(path.read_bytes()))
    python, runtime = _runtime()
    if (record.root, record.python, record.runtime, record.adapters) != (
        root,
        python,
        runtime,
        drum_adapters(),
    ):
        raise ValueError("Drum backend current runtime or adapter recipe changed")
    if record.payload != drum_payload(
        load_drum_pins(), record.artifacts, should_cancel=should_cancel
    ):
        raise ValueError("Drum backend differs from fixed original artifacts")
    verify_drum_payload(record, should_cancel)
    return record


def drum_request(record: DrumBackend, pcm: FileIdentity, model_frames: int) -> dict[str, object]:
    drum_output_rows(model_frames)
    if pcm.size_bytes != model_frames * 8:
        raise ValueError("Drum input must contain complete stereo float32 model frames")
    return dict(
        packages=str(record.root / "packages"),
        pins=str(Path(__file__).with_name("drum_pins.json")),
        pcm=pcm.model_dump(mode="json"),
        model_frames=model_frames,
    )


def verify_drum_request(
    record: DrumBackend, attempt: Path, pcm: FileIdentity, model_frames: int
) -> None:
    import json

    path = guarded_path(attempt / "request.json")
    if path.stat().st_size > 65536:
        raise ValueError("Drum request exceeds budget")
    raw = load_unique_json(path.read_bytes())
    expected = drum_request(record, pcm, model_frames)
    if json.dumps(raw, sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True, allow_nan=False
    ):
        raise ValueError("Saved drum request differs from current backend/source/geometry")


def call_drum_backend(
    record: DrumBackend,
    attempt: Path,
    pcm: FileIdentity,
    model_frames: int,
    *,
    should_cancel: Cancel = None,
) -> NativeDrumResult:
    import json
    import math
    import struct

    record = DrumBackend.model_validate(record.model_dump())
    pcm = FileIdentity.model_validate(pcm.model_dump())
    request = drum_request(record, pcm, model_frames)
    cancelled(should_cancel)
    if record != read_drum_backend(record.root, should_cancel=should_cancel):
        raise ValueError("Drum backend changed before execution")
    verify_inputs([pcm])
    attempt = guarded_path(attempt)
    protected = [
        record.root,
        pcm.path,
        *[i.path for i in [*record.runtime, *record.adapters, *record.artifacts]],
    ]
    if any(
        attempt == path or attempt.is_relative_to(path) or path.is_relative_to(attempt)
        for path in protected
    ):
        raise ValueError("Drum attempt overlaps protected inputs or backend")
    if not attempt.is_dir() or list(attempt.iterdir()):
        raise ValueError("Drum attempt must be a new empty exclusive directory")
    with (attempt / "request.json").open("x", encoding="utf-8") as stream:
        json.dump(request, stream, allow_nan=False)
    worker = Path(__file__).with_name("drum_worker.py")
    try:
        stdout, stderr = run_bounded_process(
            [str(record.python.path), "-I", "-S", "-B", str(worker), str(attempt / "request.json")],
            timeout=1800,
            should_cancel=should_cancel,
        )
    except Exception as error:
        for name in ("stdout", "stderr"):
            with (attempt / (name + ".bin")).open("xb") as output:
                output.write(getattr(error, name, b""))
        raise
    for name, raw in (("stdout", stdout), ("stderr", stderr)):
        with (attempt / (name + ".bin")).open("xb") as output:
            output.write(raw)
    verify_inputs([pcm])
    verify_drum_request(record, attempt, pcm, model_frames)
    if record != read_drum_backend(record.root, should_cancel=should_cancel):
        raise ValueError("Drum backend changed during execution")
    path = guarded_path(attempt / "result.json")
    if path.stat().st_size > 1024**2:
        raise ValueError("Drum native result exceeds budget")
    result_identity = capture_stream_input(path)
    result = NativeDrumResult.model_validate(load_unique_json(path.read_bytes()))
    pins = load_drum_pins()
    if (
        result.model_frames,
        result.source_sha256,
        result.execution.geometry,
        result.execution.versions,
    ) != (
        model_frames,
        pcm.sha256,
        pins.state,
        {p.distribution: p.version for p in pins.artifacts},
    ):
        raise ValueError("Drum native execution differs from fixed source/state/runtime")
    if set(result.execution.modules) != {"torch", "torchaudio", "numpy", "einops", "idm"} or any(
        not guarded_path(path).is_relative_to(record.root / "packages")
        for path in result.execution.modules.values()
    ):
        raise ValueError("Native drum imports escaped the isolated payload")
    witnesses = [pcm, result_identity]
    for name, artifact in result.files.items():
        cancelled(should_cancel)
        identity = capture_stream_input(attempt / name)
        if (identity.size_bytes, identity.sha256) != (artifact.size_bytes, artifact.sha256):
            raise ValueError("Complete native drum array changed or truncated")
        with identity.path.open("rb") as source_stream:
            while block := source_stream.read(1024**2):
                if not all(math.isfinite(v[0]) for v in struct.iter_unpack("<f", block)):
                    raise ValueError("Nonfinite native drum array")
        witnesses.append(identity)
    verify_inputs(witnesses)
    verify_drum_request(record, attempt, pcm, model_frames)
    cancelled(should_cancel)
    return result
