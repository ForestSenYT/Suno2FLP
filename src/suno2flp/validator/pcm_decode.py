"""Independent fixed-container parsing and inverse sample comparison against source PCM."""

import hashlib
import math
import struct
import time
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.audio_decode import (
    MAX_PCM_REPORT_BYTES,
    PCM_BLOCK_FRAMES,
    PCM_PASS_SECONDS,
    PcmDecodeReport,
    check_decode_request,
)
from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import (
    capture_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.importer.audio import inspect_audio
from suno2flp.importer.pcm_decode import pcm_runtime


def verify_pcm_decode(
    report_path: Path, *, should_cancel: Callable[[], bool] | None = None
) -> PcmDecodeReport:
    deadline = time.monotonic() + PCM_PASS_SECONDS
    check_decode_request(should_cancel, deadline)
    path = guarded_path(report_path)
    if path.stat().st_size > MAX_PCM_REPORT_BYTES:
        raise OfflineError("audio_decode_evidence_invalid", "Expected a bounded decode report")
    identity, raw = capture_input(path)
    result = PcmDecodeReport.model_validate(load_unique_json(raw))
    root = path.parent
    if (
        path.name != "decode.json"
        or result.pcm.path != root / "decoded.wav"
        or result.preflight.source.path.is_relative_to(root)
        or any((parent / "backend.json").exists() for parent in (root, *root.parents))
    ):
        raise OfflineError(
            "audio_decode_evidence_invalid", "Decode evidence paths are inconsistent"
        )
    verify_inputs([result.preflight.source, result.pcm])
    if result.runtime != pcm_runtime():
        raise OfflineError(
            "audio_runtime_changed", "Current runtime disagrees with decode evidence"
        )
    if result.preflight != inspect_audio(result.preflight.source.path):
        raise OfflineError(
            "audio_decode_evidence_invalid", "Source preflight disagrees with report"
        )
    source = result.preflight
    with result.pcm.path.open("rb") as decoded, source.source.path.open("rb") as original:
        header = decoded.read(58)
        if (
            len(header) != 58
            or header[:4] != b"RIFF"
            or header[8:16] != b"WAVEfmt "
            or struct.unpack_from("<I", header, 4)[0] != result.pcm.size_bytes - 8
            or struct.unpack_from("<IHHIIHHH", header, 16)
            != (
                18,
                3,
                source.channels,
                source.sample_rate,
                source.sample_rate * source.channels * 8,
                source.channels * 8,
                64,
                0,
            )
            or header[38:42] != b"fact"
            or struct.unpack_from("<II", header, 42) != (4, source.frames)
            or header[50:54] != b"data"
            or struct.unpack_from("<I", header, 54)[0] != source.frames * source.channels * 8
        ):
            raise OfflineError(
                "audio_decode_evidence_invalid", "Invalid complete float64 WAV header"
            )
        original.seek(source.data_offset)
        remaining = source.frames
        digest = hashlib.sha256()
        width = source.sample_width_bytes
        multiplier = 2 ** (width * 8 - 1)
        while remaining:
            check_decode_request(should_cancel, deadline)
            frames = min(remaining, PCM_BLOCK_FRAMES)
            samples = frames * source.channels
            block = decoded.read(samples * 8)
            expected = original.read(samples * width)
            if len(block) != samples * 8 or len(expected) != samples * width:
                raise OfflineError(
                    "audio_decode_evidence_invalid", "Truncated complete sample data"
                )
            recovered = bytearray()
            for (value,) in struct.iter_unpack("<d", block):
                scaled = value * multiplier
                if not math.isfinite(value) or not -1 <= value < 1 or int(scaled) != scaled:
                    raise OfflineError("audio_decode_sample_mismatch", "Invalid normalized sample")
                integer = int(scaled)
                recovered.extend(
                    bytes([integer + 128])
                    if width == 1
                    else integer.to_bytes(width, "little", signed=True)
                )
            if recovered != expected:
                raise OfflineError(
                    "audio_decode_sample_mismatch", "Decoded samples differ from source"
                )
            digest.update(block)
            remaining -= frames
        if decoded.read(1) or digest.hexdigest() != result.samples_sha256:
            raise OfflineError(
                "audio_decode_evidence_invalid", "PCM length/hash disagrees with report"
            )
    check_decode_request(should_cancel, deadline)
    verify_inputs([identity, source.source, result.pcm])
    if result.runtime != pcm_runtime():
        raise OfflineError(
            "audio_runtime_changed", "Runtime changed during independent verification"
        )
    return result
