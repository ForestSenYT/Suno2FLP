"""Separate fixed MoE preparation and bounded processes, never Single promotion."""

import json
from pathlib import Path
from typing import Literal

from suno2flp.core.codec_backend import CodecCancelled, CodecProcessError
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    new_report,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.yourmt3_moe import YourMT3MoEBackend
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.beat_backend import _runtime
from suno2flp.integrations.codec_process import run_bounded_process
from suno2flp.integrations.yourmt3_backend import verify_yourmt3_payload, yourmt3_adapters
from suno2flp.integrations.yourmt3_source import (
    load_yourmt3_moe_pins,
    safe_relative,
    yourmt3_payload,
)


def provision_yourmt3_moe_backend(output: Path, artifacts: Path) -> YourMT3MoEBackend:
    if guarded_path(output).exists():
        raise FileExistsError("MoE output already exists")
    pins = load_yourmt3_moe_pins()
    names = [p.filename for p in pins.wheels] + [p.filename for p in pins.files]
    inputs = [capture_stream_input(artifacts / safe_relative(name)) for name in names]
    python, runtime = _runtime()
    adapters = yourmt3_adapters()
    expected = yourmt3_payload(pins, inputs)
    root = new_model_directory(output, [artifacts, *[i.path for i in [*runtime, *adapters]]])
    packages = root / "packages"
    packages.mkdir()
    actual = yourmt3_payload(pins, inputs, packages)
    if actual != expected:
        raise ValueError("MoE payload changed during preparation")
    record = YourMT3MoEBackend(
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
        lambda: verify_yourmt3_payload(record),
    )
    return record


def read_yourmt3_moe_backend(root: Path) -> YourMT3MoEBackend:
    root = guarded_path(root)
    path = guarded_path(root / "backend.json")
    if path.stat().st_size > 8 * 1024**2:
        raise ValueError("MoE backend manifest exceeds budget")
    record = YourMT3MoEBackend.model_validate(load_unique_json(path.read_bytes()))
    python, runtime = _runtime()
    if (record.root, record.python, record.runtime, record.adapters) != (
        root,
        python,
        runtime,
        yourmt3_adapters(),
    ):
        raise ValueError("MoE current runtime/adapter recipe changed")
    if record.payload != yourmt3_payload(load_yourmt3_moe_pins(), record.artifacts):
        raise ValueError("MoE payload differs from fixed artifacts")
    verify_yourmt3_payload(record)
    return record


def yourmt3_moe_request(
    record: YourMT3MoEBackend,
    pcm: FileIdentity,
    frames: int,
    sample_rate: int,
    channels: int,
    *,
    mode: Literal["infer", "decode"] = "infer",
    raw: Path | None = None,
) -> dict[str, object]:
    return dict(
        mode=mode,
        packages=str(record.root / "packages"),
        pins=str(Path(__file__).with_name("yourmt3_moe_pins.json")),
        pcm=pcm.model_dump(mode="json"),
        frames=frames,
        sample_rate=sample_rate,
        channels=channels,
        raw=str(raw) if raw else None,
    )


def call_yourmt3_moe_backend(
    record: YourMT3MoEBackend, attempt: Path, request: dict[str, object]
) -> FileIdentity:
    if record != read_yourmt3_moe_backend(record.root):
        raise ValueError("MoE backend changed before execution")
    attempt = guarded_path(attempt)
    if attempt.exists():
        raise FileExistsError("MoE invocation output already exists")
    new_model_directory(attempt, [record.root, *[i.path for i in record.artifacts]])
    request_path = attempt / "request.json"
    new_report(request_path, json.dumps(request, indent=2, allow_nan=False), [])
    identity = capture_stream_input(request_path)
    worker = Path(__file__).with_name("yourmt3_moe_worker.py")
    try:
        stdout, stderr = run_bounded_process(
            [str(record.python.path), "-I", "-S", "-B", str(worker), str(request_path)],
            timeout=2700,
            max_bytes=2 * 1024**2,
        )
    except (CodecProcessError, CodecCancelled) as error:
        for name, content in (("stdout.txt", error.stdout), ("stderr.txt", error.stderr)):
            with guarded_path(attempt / name).open("xb") as stream:
                stream.write(content)
        raise
    for name, content in (("stdout.txt", stdout), ("stderr.txt", stderr)):
        with guarded_path(attempt / name).open("xb") as stream:
            stream.write(content)
    verify_inputs([identity])
    if record != read_yourmt3_moe_backend(record.root):
        raise ValueError("MoE backend changed during execution")
    raw = guarded_path(attempt / "native.json")
    if raw.stat().st_size > 64 * 1024**2:
        raise ValueError("MoE complete native result exceeds budget")
    return capture_stream_input(raw)
