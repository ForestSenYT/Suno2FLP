"""Stream explicitly aligned PCM WAV comparisons without rendering or inference."""

import math
import struct
import wave
from collections.abc import Iterator
from pathlib import Path

from suno2flp.core.audio_quality import RenderComparisonReport
from suno2flp.core.errors import OfflineError, Suno2FLPError
from suno2flp.core.models import Diagnostic
from suno2flp.core.offline_files import capture_stream_input, verify_inputs


def _integers(raw: bytes, width: int) -> Iterator[int]:
    for offset in range(0, len(raw), width):
        if width == 1:
            yield raw[offset] - 128  # WAV PCM8 is unsigned; other integer PCM is signed LE.
        else:
            yield int.from_bytes(raw[offset : offset + width], "little", signed=True)


def _validate_pcm_layout(path: Path, audio: wave.Wave_read) -> None:
    """Check declared extents independently of wave's floored frame count."""
    frame_width = audio.getnchannels() * audio.getsampwidth()
    format_chunks = data_chunks = 0
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise OfflineError("pcm_format_unsupported", "Only little-endian RIFF/WAVE supported")
        end = int.from_bytes(header[4:8], "little") + 8
        if end != path.stat().st_size:
            raise OfflineError("pcm_extent_invalid", "Declared RIFF size differs from file size")
        position = 12
        while position < end:
            if end - position < 8:
                raise OfflineError("pcm_truncated", "Incomplete RIFF chunk header")
            stream.seek(position)
            chunk = stream.read(8)
            if len(chunk) != 8:
                raise OfflineError("pcm_truncated", "Incomplete RIFF chunk header")
            tag, size = chunk[:4], int.from_bytes(chunk[4:], "little")
            payload_end = position + 8 + size
            if payload_end > end:
                raise OfflineError("pcm_truncated", "Chunk payload exceeds declared RIFF extent")
            if tag == b"fmt ":
                format_chunks += 1
                if size < 16:
                    raise OfflineError("pcm_format_unsupported", "Incomplete PCM format header")
                fmt = stream.read(16)
                expected = (
                    1,
                    audio.getnchannels(),
                    audio.getframerate(),
                    audio.getframerate() * frame_width,
                    frame_width,
                    audio.getsampwidth() * 8,
                )
                if len(fmt) != 16 or struct.unpack("<HHIIHH", fmt) != expected:
                    raise OfflineError(
                        "pcm_format_unsupported", "Classic integer PCM format fields must agree"
                    )
            elif tag == b"data":
                data_chunks += 1
                if size % frame_width or size != audio.getnframes() * frame_width:
                    raise OfflineError("pcm_frame_invalid", "PCM data must contain whole frames")
            position = payload_end + (size & 1)
            # stdlib wave writes terminal odd PCM8 data without a pad; no next chunk is hidden.
            if position == end + 1 and payload_end == end and tag == b"data":
                position = end
            if position > end:
                raise OfflineError("pcm_truncated", "Missing RIFF chunk padding")
        if format_chunks != 1 or data_chunks != 1:
            raise OfflineError("pcm_layout_unsupported", "Exactly one fmt and data chunk required")


def compare_renders(
    reference: Path,
    candidate: Path,
    *,
    max_rms_error: float | None = None,
) -> RenderComparisonReport:
    if max_rms_error is not None and (not math.isfinite(max_rms_error) or max_rms_error < 0):
        raise OfflineError("pcm_threshold_invalid", "RMS tolerance must be finite and nonnegative")
    report = RenderComparisonReport(max_rms_error=max_rms_error)
    files = []
    try:
        files.append(capture_stream_input(reference))
        files.append(capture_stream_input(candidate))
        with (
            wave.open(str(files[0].path), "rb") as left,
            wave.open(str(files[1].path), "rb") as right,
        ):
            report.sample_rate = left.getframerate()
            report.channels = left.getnchannels()
            report.sample_width_bytes = left.getsampwidth()
            report.frames_reference = left.getnframes()
            report.frames_candidate = right.getnframes()
            shape = (
                left.getframerate(),
                left.getnchannels(),
                left.getsampwidth(),
                left.getnframes(),
            )
            if shape != (
                right.getframerate(),
                right.getnchannels(),
                right.getsampwidth(),
                right.getnframes(),
            ):
                raise OfflineError(
                    "pcm_shape_mismatch", "Sample rate, channels, width and frame count must match"
                )
            width = left.getsampwidth()
            channels = left.getnchannels()
            if (
                left.getcomptype() != "NONE"
                or right.getcomptype() != "NONE"
                or width not in {1, 2, 3, 4}
            ):
                raise OfflineError(
                    "pcm_format_unsupported", "Only uncompressed integer PCM8/16/24/32 supported"
                )
            if not left.getnframes():
                raise OfflineError("pcm_empty", "Empty audio cannot establish a comparison")
            _validate_pcm_layout(files[0].path, left)
            _validate_pcm_layout(files[1].path, right)
            denominator = 2 ** (8 * width - 1)
            reference_energy = candidate_energy = difference_energy = maximum = 0.0
            reference_full_scale = candidate_full_scale = samples = 0
            identical = True
            remaining = left.getnframes()
            chunk_frames = max(1, 65536 // (width * channels))
            while remaining:
                count = min(remaining, chunk_frames)
                a, b = left.readframes(count), right.readframes(count)
                expected = count * channels * width
                if len(a) != expected or len(b) != expected:
                    raise OfflineError(
                        "pcm_truncated", "PCM payload is shorter than declared frames"
                    )
                identical = identical and a == b
                for x, y in zip(_integers(a, width), _integers(b, width), strict=True):
                    ref, actual = x / denominator, y / denominator
                    difference = ref - actual
                    reference_energy += ref * ref
                    candidate_energy += actual * actual
                    difference_energy += difference * difference
                    maximum = max(maximum, abs(difference))
                    reference_full_scale += int(x == -denominator or x == denominator - 1)
                    candidate_full_scale += int(y == -denominator or y == denominator - 1)
                samples += count * channels
                remaining -= count
            report.compared_samples = samples
            report.reference_full_scale_samples = reference_full_scale
            report.candidate_full_scale_samples = candidate_full_scale
            report.reference_rms = math.sqrt(reference_energy / samples)
            report.candidate_rms = math.sqrt(candidate_energy / samples)
            report.rms_difference = math.sqrt(difference_energy / samples)
            report.max_abs_difference = maximum
            report.samples_identical = identical
            if max_rms_error is not None:
                report.within_tolerance = report.rms_difference <= max_rms_error
                if not report.within_tolerance:
                    report.diagnostics.append(
                        Diagnostic(
                            code="pcm_tolerance_exceeded",
                            severity="error",
                            message="Numerical RMS difference exceeds explicit tolerance",
                        )
                    )
    except (OSError, EOFError, ValueError, wave.Error, Suno2FLPError) as exc:
        report.diagnostics.append(
            Diagnostic(
                code=getattr(exc, "code", "pcm_input_invalid"), severity="error", message=str(exc)
            )
        )
        report.samples_identical = None
        report.within_tolerance = None
    report.input_files = files
    try:
        verify_inputs(files)
    except (OSError, RuntimeError, ValueError, Suno2FLPError) as exc:
        report.diagnostics.append(
            Diagnostic(code="pcm_input_changed", severity="error", message=str(exc))
        )
        report.samples_identical = None
        report.within_tolerance = None
    report.valid = not report.diagnostics
    return report
