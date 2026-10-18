"""Explicit development-only audio transcription; never grants FLP eligibility."""

from pathlib import Path

from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.yourmt3 import (
    FrameInterval,
    YourMT3Candidate,
    summarize_yourmt3,
    validate_yourmt3_intervals,
)
from suno2flp.core.yourmt3_native import YourMT3Native, check_yourmt3_native
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.yourmt3_backend import (
    call_yourmt3_backend,
    read_yourmt3_backend,
    yourmt3_request,
)
from suno2flp.validator.pcm_decode import verify_pcm_decode
from suno2flp.validator.yourmt3 import verify_yourmt3_record


def transcribe_yourmt3(
    decode_report: Path, backend_root: Path, output: Path, intervals: list[FrameInterval]
) -> YourMT3Candidate:
    if guarded_path(output).exists():
        raise FileExistsError("YourMT3 candidate output already exists")
    intervals = [FrameInterval.model_validate(i.model_dump()) for i in intervals]
    decode_identity = capture_stream_input(decode_report)
    decode = verify_pcm_decode(decode_report)
    source = decode.preflight
    validate_yourmt3_intervals(intervals, source.frames)
    backend = read_yourmt3_backend(backend_root)
    backend_identity = capture_stream_input(backend.root / "backend.json")
    protected = [decode_identity, source.source, decode.pcm, backend_identity]
    root = new_model_directory(output, [backend.root, *[i.path for i in protected]])
    request = yourmt3_request(
        backend, decode.pcm, source.frames, source.sample_rate, source.channels
    )
    raw = call_yourmt3_backend(backend, root / "attempt", request)
    native = YourMT3Native.model_validate(load_unique_json(raw.path.read_bytes()))
    check_yourmt3_native(native, source.frames, source.sample_rate)
    record = YourMT3Candidate(
        root=root,
        backend=backend_identity,
        decode_report=decode_identity,
        source_audio=source.source,
        pcm=decode.pcm,
        frames=source.frames,
        sample_rate=source.sample_rate,
        channels=1 if source.channels == 1 else 2,
        intervals=intervals,
        raw=raw,
        request=capture_stream_input(root / "attempt/request.json"),
        diagnostics=[
            capture_stream_input(root / "attempt" / name) for name in ("stdout.txt", "stderr.txt")
        ],
        summaries=summarize_yourmt3(native.notes, intervals, source.sample_rate),
    )

    def final_check() -> None:
        verify_inputs(protected)
        verify_yourmt3_record(record)

    publish_verified_report(
        root / "yourmt3.json",
        record.model_dump_json(indent=2),
        [i.path for i in protected],
        final_check,
    )
    return record
