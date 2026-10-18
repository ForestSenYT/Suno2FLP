"""Current-source, per-channel generation and independent token-decoding checks."""

import json
import uuid
from pathlib import Path

from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.yourmt3 import summarize_yourmt3
from suno2flp.core.yourmt3_moe import (
    YourMT3MoECandidate,
    YourMT3MoENative,
    check_yourmt3_moe_native,
)
from suno2flp.integrations.yourmt3_moe_backend import (
    call_yourmt3_moe_backend,
    read_yourmt3_moe_backend,
    yourmt3_moe_request,
)
from suno2flp.integrations.yourmt3_source import load_yourmt3_moe_pins
from suno2flp.integrations.yourmt3_worker import configurations_match
from suno2flp.validator.pcm_decode import verify_pcm_decode


def verify_yourmt3_moe_record(record: YourMT3MoECandidate) -> None:
    record = YourMT3MoECandidate.model_validate(record.model_dump())
    root = guarded_path(record.root)
    if [record.raw.path, record.request.path, *[i.path for i in record.diagnostics]] != [
        root / "attempt/native.json",
        root / "attempt/request.json",
        root / "attempt/stdout.txt",
        root / "attempt/stderr.txt",
    ]:
        raise ValueError("MoE evidence paths differ from exclusive candidate layout")
    inputs = [
        record.backend,
        record.decode_report,
        record.source_audio,
        record.pcm,
        record.raw,
        record.request,
        *record.diagnostics,
    ]
    verify_inputs(inputs)
    decode = verify_pcm_decode(record.decode_report.path)
    if (record.source_audio, record.pcm, record.frames, record.sample_rate, record.channels) != (
        decode.preflight.source,
        decode.pcm,
        decode.preflight.frames,
        decode.preflight.sample_rate,
        decode.preflight.channels,
    ):
        raise ValueError("MoE source snapshot differs from independently verified PCM")
    if record.backend.path.name != "backend.json":
        raise ValueError("Expected a complete fixed MoE backend")
    backend = read_yourmt3_moe_backend(record.backend.path.parent)
    if record.raw.size_bytes > 64 * 1024**2 or record.request.size_bytes > 65536:
        raise ValueError("MoE complete raw evidence exceeds budget")
    native = YourMT3MoENative.model_validate(load_unique_json(record.raw.path.read_bytes()))
    check_yourmt3_moe_native(native, record.frames, record.sample_rate)
    pins = load_yourmt3_moe_pins()
    if not configurations_match(native.configuration, pins.configuration) or native.versions != {
        p.distribution: p.version for p in pins.wheels
    }:
        raise ValueError("MoE native runtime/configuration differs from fixed profile")
    request = yourmt3_moe_request(
        backend, record.pcm, record.frames, record.sample_rate, record.channels
    )
    if load_unique_json(record.request.path.read_bytes()) != request:
        raise ValueError("Saved MoE request differs from current source and backend")
    notes = [note for channel in native.channels for note in channel.notes]
    unresolved = [
        (window.index, channel)
        for window in native.windows
        for channel in window.unresolved_channels
    ]
    if record.summaries != summarize_yourmt3(notes, record.intervals, record.sample_rate) or (
        record.unresolved_generations != unresolved
    ):
        raise ValueError("MoE summary or unfinished-generation addresses differ from raw evidence")
    attempt = root.parent / f"yourmt3-moe-token-replay-{uuid.uuid4().hex}"
    replay_request = yourmt3_moe_request(
        backend,
        record.pcm,
        record.frames,
        record.sample_rate,
        record.channels,
        mode="decode",
        raw=record.raw.path,
    )
    replay = call_yourmt3_moe_backend(backend, attempt, replay_request)
    expected = {"channels": native.model_dump(mode="json")["channels"]}
    actual = load_unique_json(replay.path.read_bytes())
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True, allow_nan=False
    ):
        raise ValueError(
            "Independent MoE token decoding disagrees with complete13-channel evidence"
        )
    verify_inputs([*inputs, replay])


def verify_yourmt3_moe(candidate_path: Path) -> YourMT3MoECandidate:
    path = guarded_path(candidate_path)
    if path.name != "yourmt3-moe.json" or path.stat().st_size > 1024**2:
        raise ValueError("Expected a bounded complete MoE candidate report")
    identity = capture_stream_input(path)
    record = YourMT3MoECandidate.model_validate(load_unique_json(path.read_bytes()))
    if record.root != path.parent:
        raise ValueError("MoE report root differs from current location")
    verify_yourmt3_moe_record(record)
    verify_inputs([identity])
    return record
