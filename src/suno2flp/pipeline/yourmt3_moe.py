"""Source-bound MoE candidates, preserving every channel and generation attempt."""

from pathlib import Path

from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.yourmt3 import FrameInterval, summarize_yourmt3, validate_yourmt3_intervals
from suno2flp.core.yourmt3_moe import (
    YourMT3MoECandidate,
    YourMT3MoENative,
    check_yourmt3_moe_native,
)
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.yourmt3_moe_backend import (
    call_yourmt3_moe_backend,
    read_yourmt3_moe_backend,
    yourmt3_moe_request,
)
from suno2flp.validator.pcm_decode import verify_pcm_decode
from suno2flp.validator.yourmt3_moe import verify_yourmt3_moe_record


def transcribe_yourmt3_moe(
    decode_report: Path, backend_root: Path, output: Path, intervals: list[FrameInterval]
) -> YourMT3MoECandidate:
    if guarded_path(output).exists():
        raise FileExistsError("MoE candidate output already exists")
    intervals = [FrameInterval.model_validate(i.model_dump()) for i in intervals]
    decode_identity = capture_stream_input(decode_report)
    decode = verify_pcm_decode(decode_report)
    source = decode.preflight
    validate_yourmt3_intervals(intervals, source.frames)
    backend = read_yourmt3_moe_backend(backend_root)
    backend_identity = capture_stream_input(backend.root / "backend.json")
    protected = [decode_identity, source.source, decode.pcm, backend_identity]
    root = new_model_directory(output, [backend.root, *[i.path for i in protected]])
    request = yourmt3_moe_request(
        backend, decode.pcm, source.frames, source.sample_rate, source.channels
    )
    raw = call_yourmt3_moe_backend(backend, root / "attempt", request)
    native = YourMT3MoENative.model_validate(load_unique_json(raw.path.read_bytes()))
    check_yourmt3_moe_native(native, source.frames, source.sample_rate)
    record = YourMT3MoECandidate(
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
        summaries=summarize_yourmt3(
            [n for c in native.channels for n in c.notes], intervals, source.sample_rate
        ),
        unresolved_generations=[
            (w.index, c) for w in native.windows for c in w.unresolved_channels
        ],
    )

    def final_check() -> None:
        verify_inputs(protected)
        verify_yourmt3_moe_record(record)

    publish_verified_report(
        root / "yourmt3-moe.json",
        record.model_dump_json(indent=2),
        [i.path for i in protected],
        final_check,
    )
    return record
