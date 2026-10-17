"""Independent full-array, chunk, downmix, clock and peak readback."""

import math
import struct
from collections.abc import Callable
from pathlib import Path

from suno2flp.core.beat_native import NativeBeatResult
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import guarded_path, verify_inputs
from suno2flp.core.offline_models import FileIdentity
from suno2flp.integrations.beat_backend import cancelled
from suno2flp.validator.beat_postprocessing import BeatPeaks, reconstruct_beats


def validate_native_beats(
    attempt: Path,
    result: NativeBeatResult,
    pcm: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[BeatPeaks, list[FileIdentity]]:
    result = NativeBeatResult.model_validate(result.model_dump())
    attempt = guarded_path(attempt)
    cancelled(should_cancel)
    identities = capture_file_tree(attempt, should_cancel=should_cancel)
    by_name = {f.path.relative_to(attempt).as_posix(): f for f in identities}
    data_names = {
        n for n in by_name if n not in {"request.json", "result.json", "stdout.bin", "stderr.bin"}
    }
    if data_names != set(result.files):
        raise ValueError("Native beat file membership changed")
    raw: dict[str, bytes] = {}
    for name, array in result.files.items():
        if (
            name not in by_name
            or by_name[name].sha256 != array.sha256
            or by_name[name].size_bytes != array.size_bytes
        ):
            raise ValueError("Native array identity changed")
        data = by_name[name].path.read_bytes()
        numeric_format = "<f" if array.encoding == "<f4" else "<d"
        if any(not math.isfinite(v[0]) for v in struct.iter_unpack(numeric_format, data)):
            raise ValueError("Nonfinite native array values")
        raw[name] = data

    def shape(name: str, dimensions: list[int], encoding: str) -> bytes:
        if (
            name not in result.files
            or result.files[name].shape != dimensions
            or result.files[name].encoding != encoding
        ):
            raise ValueError(f"Complete native array shape changed: {name}")
        return raw[name]

    frames, rate = result.frames, result.sample_rate
    mono = shape("mono.f64", [frames], "<f8")
    model_frames = result.files["resampled.f64"].shape[0]
    # Soxr's boundary rounding is recorded rather than used as a new song clock.
    lower, remainder = divmod(frames * 22050, rate)
    if model_frames not in {lower, lower + bool(remainder)} or model_frames <= 512:
        raise ValueError("Resampling lost the complete original duration")
    resampled = shape("resampled.f64", [model_frames], "<f8")
    wave = shape("wave.f32", [model_frames], "<f4")
    if rate == 22050 and mono != resampled:
        raise ValueError("Same-rate mono samples changed")
    for i, (v,) in enumerate(struct.iter_unpack("<d", resampled)):
        if wave[i * 4 : i * 4 + 4] != struct.pack("<f", v):
            raise ValueError("Model float32 conversion changed")
    pcm = guarded_path(pcm)
    if pcm.stat().st_size != 58 + frames * result.channels * 8:
        raise ValueError("Original PCM geometry changed")
    source_peak, mono_peak = 0.0, 0.0
    with pcm.open("rb") as stream:
        stream.seek(58)
        position = 0
        while block := stream.read(4096 * result.channels * 8):
            cancelled(should_cancel)
            for values in struct.iter_unpack("<" + "d" * result.channels, block):
                if any(not math.isfinite(v) or abs(v) > 1 for v in values):
                    raise ValueError("Invalid original PCM samples")
                value = sum(values) / result.channels
                if mono[position * 8 : position * 8 + 8] != struct.pack("<d", value):
                    raise ValueError("Original source-order downmix changed")
                source_peak = max(source_peak, *map(abs, values))
                mono_peak = max(mono_peak, abs(value))
                position += 1
    if (source_peak, mono_peak) != (result.source_peak, result.mono_peak):
        raise ValueError("Native source signal observations changed")
    count = model_frames // 441 + 1
    spect = shape("spect.f32", [count, 128], "<f4")
    starts = list(range(-6, count - 6, 1488))
    if count > 1488:
        starts[-1] = count - 1494
    if result.chunk_starts != starts:
        raise ValueError("Native chunk overlap or tail coverage changed")
    required = {
        "mono.f64",
        "resampled.f64",
        "wave.f32",
        "spect.f32",
        "beat.f32",
        "downbeat.f32",
        "beats.f64",
        "downbeats.f64",
    }
    reconstructed = {name: bytearray(count * 4) for name in ("beat", "downbeat")}
    covered: set[int] = set()
    for i in reversed(range(len(starts))):
        cancelled(should_cancel)
        start = starts[i]
        left, end = max(start, 0), min(start + 1500, count)
        pad_left, pad_right = max(0, -start), max(0, min(6, start + 1500 - count))
        chunk_frames = end - left + pad_left + pad_right
        expected_input = (
            bytes(pad_left * 512) + spect[left * 512 : end * 512] + bytes(pad_right * 512)
        )
        name = f"chunk-{i}-input.f32"
        required.add(name)
        if shape(name, [chunk_frames, 128], "<f4") != expected_input:
            raise ValueError("Complete chunk input or padding changed")
        effective_start = start + 6
        effective_end = effective_start + chunk_frames - 12
        if not 0 <= effective_start < effective_end <= count:
            raise ValueError("Invalid native chunk aggregation range")
        covered.update(range(effective_start, effective_end))
        for kind in reconstructed:
            name = f"chunk-{i}-{kind}.f32"
            required.add(name)
            prediction = shape(name, [chunk_frames], "<f4")
            reconstructed[kind][effective_start * 4 : effective_end * 4] = prediction[24:-24]
    if required != set(result.files) or covered != set(range(count)):
        raise ValueError("Incomplete native raw chunk or source coverage")
    for kind, aggregate in reconstructed.items():
        if shape(f"{kind}.f32", [count], "<f4") != aggregate:
            raise ValueError("Native aggregation differs from full raw predictions")
    peaks = reconstruct_beats(raw["beat.f32"], raw["downbeat.f32"])
    for name, positions in (
        ("beats.f64", peaks.beat_frames),
        ("downbeats.f64", peaks.aligned_downbeat_frames),
    ):
        expected = b"".join(struct.pack("<d", float(f) / 50) for f in positions)
        if shape(name, [len(positions)], "<f8") != expected:
            raise ValueError("Native minimal peak/alignment output changed")
    verify_inputs(identities)
    cancelled(should_cancel)
    return peaks, identities
