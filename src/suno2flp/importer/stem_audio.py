"""Exact finite float32 estimate widening; never an original-recording decoder."""

import math
import os
import struct
import time
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import check_decode_request
from suno2flp.core.offline_files import capture_stream_input, guarded_path, verify_inputs
from suno2flp.core.offline_models import FileIdentity


def widen_stem_wave(
    source: Path,
    output: Path,
    *,
    frames: int,
    sample_rate: int,
    channels: int,
    should_cancel: Callable[[], bool] | None = None,
) -> FileIdentity:
    """Preserve N/Fs/C and every finite IEEE value, including negative zero."""
    if (
        any(type(value) is not int for value in (frames, sample_rate, channels))
        or not 8000 <= sample_rate <= 192000
        or channels not in (1, 2)
        or not 0 < frames <= sample_rate * 600
    ):
        raise ValueError("Use mono/stereo original source geometry within 600 seconds")
    deadline = time.monotonic() + 300
    check_decode_request(should_cancel, deadline)
    identity = capture_stream_input(source)
    destination = guarded_path(output)
    if (
        destination.exists()
        or not destination.parent.is_dir()
        or any((parent / "backend.json").exists() for parent in destination.parents)
    ):
        raise ValueError("Use an exclusive new waveform outside inputs and backends")

    def header(bits: int) -> bytes:
        width = channels * (bits // 8)
        size = frames * width
        return struct.pack(
            "<4sI4s4sIHHIIHHH4sII4sI",
            b"RIFF",
            size + 50,
            b"WAVE",
            b"fmt ",
            18,
            3,
            channels,
            sample_rate,
            sample_rate * width,
            width,
            bits,
            0,
            b"fact",
            4,
            frames,
            b"data",
            size,
        )

    if identity.size_bytes != 58 + frames * channels * 4:
        raise ValueError("Complete estimated float32 waveform size differs from source clock")
    with identity.path.open("rb") as stream:
        if stream.read(58) != header(32):
            raise ValueError("Estimated source must have the canonical complete float32 header")
        with destination.open("xb") as target:
            target.write(header(64))
            remaining = frames * channels * 4
            while remaining:
                check_decode_request(should_cancel, deadline)
                raw = stream.read(min(4096 * channels * 4, remaining))
                if len(raw) != min(4096 * channels * 4, remaining):
                    raise ValueError("Estimated source changed or was truncated during widening")
                values = [value[0] for value in struct.iter_unpack("<f", raw)]
                if any(not math.isfinite(value) for value in values):
                    raise ValueError("Estimated samples must all be finite")
                target.write(struct.pack(f"<{len(values)}d", *values))
                remaining -= len(raw)
            if stream.read(1):
                raise ValueError("Estimated source has an unexpected tail")
            target.flush()
            os.fsync(target.fileno())
    verify_inputs([identity])
    check_decode_request(should_cancel, deadline)
    return capture_stream_input(destination)
