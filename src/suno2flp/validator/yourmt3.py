"""Independent current-file, source-clock, raw-token decoding and summary checks."""

import json
import uuid
from pathlib import Path

from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.yourmt3 import YourMT3Candidate, summarize_yourmt3
from suno2flp.core.yourmt3_native import YourMT3Native, check_yourmt3_native
from suno2flp.integrations.yourmt3_backend import (
    call_yourmt3_backend,
    read_yourmt3_backend,
    yourmt3_request,
)
from suno2flp.integrations.yourmt3_source import load_yourmt3_pins
from suno2flp.integrations.yourmt3_worker import configurations_match
from suno2flp.validator.pcm_decode import verify_pcm_decode


def verify_yourmt3_record(record: YourMT3Candidate) -> None:
    record = YourMT3Candidate.model_validate(record.model_dump())
    root = guarded_path(record.root)
    expected = [
        root / "attempt/native.json",
        root / "attempt/request.json",
        root / "attempt/stdout.txt",
        root / "attempt/stderr.txt",
    ]
    if [record.raw.path, record.request.path, *[i.path for i in record.diagnostics]] != expected:
        raise ValueError("YourMT3 evidence paths differ from exclusive candidate layout")
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
        raise ValueError("YourMT3 source snapshot differs from verified original PCM")
    if record.backend.path.name != "backend.json":
        raise ValueError("Expected a complete fixed YourMT3 backend manifest")
    backend = read_yourmt3_backend(record.backend.path.parent)
    if record.raw.size_bytes > 16 * 1024**2 or record.request.size_bytes > 65536:
        raise ValueError("YourMT3 raw evidence exceeds budget")
    native = YourMT3Native.model_validate(load_unique_json(record.raw.path.read_bytes()))
    check_yourmt3_native(native, record.frames, record.sample_rate)
    pins = load_yourmt3_pins()
    if not configurations_match(native.configuration, pins.configuration) or native.versions != {
        p.distribution: p.version for p in pins.wheels
    }:
        raise ValueError("YourMT3 native runtime/configuration differs from fixed profile")
    request = yourmt3_request(
        backend, record.pcm, record.frames, record.sample_rate, record.channels
    )
    if load_unique_json(record.request.path.read_bytes()) != request:
        raise ValueError("Saved YourMT3 request differs from current source and backend")
    if record.summaries != summarize_yourmt3(native.notes, record.intervals, record.sample_rate):
        raise ValueError("YourMT3 interval summaries differ from complete original-clock notes")
    # Keep the original candidate read-only. Replay into a distinct retained sibling directory.
    attempt = root.parent / f"yourmt3-token-replay-{uuid.uuid4().hex}"
    replay_request = yourmt3_request(
        backend,
        record.pcm,
        record.frames,
        record.sample_rate,
        record.channels,
        mode="decode",
        raw=record.raw.path,
    )
    replay = call_yourmt3_backend(backend, attempt, replay_request)
    fields = ("notes", "decoded_windows", "events", "decode_errors", "merge_errors")
    expected_decoded = {k: native.model_dump(mode="json")[k] for k in fields}
    actual = load_unique_json(replay.path.read_bytes())
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(
        expected_decoded, sort_keys=True, allow_nan=False
    ):
        raise ValueError("Independent YourMT3 token decoding disagrees with native result")
    verify_inputs([*inputs, replay])


def verify_yourmt3(candidate_path: Path) -> YourMT3Candidate:
    path = guarded_path(candidate_path)
    if path.name != "yourmt3.json" or path.stat().st_size > 1024**2:
        raise ValueError("Expected a bounded complete YourMT3 candidate report")
    identity = capture_stream_input(path)
    record = YourMT3Candidate.model_validate(load_unique_json(path.read_bytes()))
    if record.root != path.parent:
        raise ValueError("YourMT3 candidate root differs from current file")
    verify_yourmt3_record(record)
    verify_inputs([identity])
    return record
