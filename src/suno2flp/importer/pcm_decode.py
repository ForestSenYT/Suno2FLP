"""Bounded standard-library decoding, with exclusive new files and no resampling."""

import hashlib
import os
import platform
import struct
import sys
import time
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import (
    MAX_PCM_REPORT_BYTES,
    PCM_BLOCK_FRAMES,
    PCM_PASS_SECONDS,
    PcmDecodeReport,
    PcmDecodeRuntime,
    check_decode_request,
)
from suno2flp.core.audio_input import AudioPreflightError
from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input, guarded_path, verify_inputs
from suno2flp.importer.audio import inspect_audio


def pcm_runtime() -> PcmDecodeRuntime:
    """Current local identities, not an authenticity or Python-distribution attestation."""
    package = Path(__file__).resolve().parent.parent
    if sys.float_info.radix != 2 or sys.float_info.mant_dig != 53:
        raise OfflineError("audio_runtime_unavailable", "IEEE binary64 Python floats are required")
    return PcmDecodeRuntime(
        implementation=platform.python_implementation(),
        python_version=sys.version,
        executable=capture_stream_input(Path(sys.executable).resolve()),
        decoder=capture_stream_input(package / "importer/pcm_decode.py"),
        verifier=capture_stream_input(package / "validator/pcm_decode.py"),
        preflight=capture_stream_input(package / "importer/audio.py"),
        contract=capture_stream_input(package / "core/audio_decode.py"),
    )


def _float_block(raw: bytes, width: int) -> bytes:
    if width == 1:
        values = [value - 128 for value in raw]
    elif width in (2, 4):
        values = [value[0] for value in struct.iter_unpack("<h" if width == 2 else "<i", raw)]
    else:
        values = [
            int.from_bytes(raw[index : index + 3], "little", signed=True)
            for index in range(0, len(raw), 3)
        ]
    divisor = 1 << (width * 8 - 1)
    return struct.pack(f"<{len(values)}d", *(value / divisor for value in values))


def decode_pcm_wave(
    source: Path,
    output_directory: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> PcmDecodeReport:
    deadline = time.monotonic() + PCM_PASS_SECONDS
    check_decode_request(should_cancel, deadline)
    preflight = inspect_audio(source)
    runtime = pcm_runtime()
    root = guarded_path(output_directory)
    if (
        root.exists()
        or not root.parent.is_dir()
        or preflight.source.path.is_relative_to(root)
        or any((parent / "backend.json").exists() for parent in (root, *root.parents))
    ):
        raise OfflineError("audio_decode_output_unsafe", "Use a new directory outside all inputs")
    check_decode_request(should_cancel, deadline)
    root.mkdir()
    destination = root / "decoded.wav"
    data_size = preflight.frames * preflight.channels * 8
    # WAVEFORMATEX(IEEE_FLOAT, 64-bit, cbSize=0), fact frames and data, all little-endian.
    header = struct.pack(
        "<4sI4s4sIHHIIHHH4sII4sI",
        b"RIFF",
        50 + data_size,
        b"WAVE",
        b"fmt ",
        18,
        3,
        preflight.channels,
        preflight.sample_rate,
        preflight.sample_rate * preflight.channels * 8,
        preflight.channels * 8,
        64,
        0,
        b"fact",
        4,
        preflight.frames,
        b"data",
        data_size,
    )
    digest = hashlib.sha256()
    with preflight.source.path.open("rb") as original, destination.open("xb") as output:
        output.write(header)
        original.seek(preflight.data_offset)
        remaining = preflight.data_bytes
        block_size = PCM_BLOCK_FRAMES * preflight.channels * preflight.sample_width_bytes
        while remaining:
            check_decode_request(should_cancel, deadline)
            raw = original.read(min(block_size, remaining))
            if len(raw) != min(block_size, remaining):
                raise OfflineError(
                    "offline_input_changed", "Source PCM was truncated during decode"
                )
            decoded = _float_block(raw, preflight.sample_width_bytes)
            output.write(decoded)
            digest.update(decoded)
            remaining -= len(raw)
        output.flush()
        os.fsync(output.fileno())
    check_decode_request(should_cancel, deadline)
    verify_inputs([preflight.source])
    if runtime != pcm_runtime():
        raise OfflineError("audio_runtime_changed", "Decoder runtime changed during decode")
    result = PcmDecodeReport(
        preflight=preflight,
        runtime=runtime,
        pcm=capture_stream_input(destination),
        samples_sha256=digest.hexdigest(),
        duration_microseconds=preflight.duration_microseconds,
    )
    raw_report = (result.model_dump_json(indent=2) + "\n").encode("utf-8")
    if len(raw_report) > MAX_PCM_REPORT_BYTES:
        raise AudioPreflightError(
            "audio_limits_exceeded", "Complete decode provenance exceeds 1 MiB", blocked=True
        )
    with (root / "decode.json").open("xb") as report:
        report.write(raw_report)
        report.flush()
        os.fsync(report.fileno())
    # The caller must independently verify before recording a completed stage.
    return result
