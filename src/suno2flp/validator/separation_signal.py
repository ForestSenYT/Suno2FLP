"""Independent streaming checks of complete source/model/partition signal evidence.

Uses the standard library, not the native worker or its numerical libraries.
It checks assembly and conservation, not the model's musical correctness.
"""

from __future__ import annotations

import math
import struct
import sys
from array import array
from collections.abc import Callable
from contextlib import ExitStack

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.separation import SeparationCandidate


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise DecodeCancelled()


def _floats(raw: bytes) -> array[float]:
    values: array[float] = array("f")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if any(not math.isfinite(value) for value in values):
        raise ValueError("All complete native float32 artifacts must be finite")
    return values


def _little(values: array[float]) -> bytes:
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def _inputs(report: SeparationCandidate, cancel: Callable[[], bool] | None) -> None:
    with report.model_input.path.open("rb") as model:
        for part in report.partitions:
            p = part.partition
            with part.input.path.open("rb") as source:
                for start in range(0, p.waveform_frames, 4096):
                    _cancel(cancel)
                    count = min(4096, p.waveform_frames - start)
                    low = max(0, p.virtual_start + start)
                    high = min(report.result.model_frames, p.virtual_start + start + count)
                    raw = source.read(count * 8)
                    _floats(raw)
                    expected = bytearray(count * 8)
                    if high > low:
                        model.seek(low * 8)
                        offset = (low - p.virtual_start - start) * 8
                        expected[offset : offset + (high - low) * 8] = model.read((high - low) * 8)
                    if raw != expected:
                        raise ValueError("Partition input is not the complete padded global source")
    with ExitStack() as stack:
        model = stack.enter_context(report.model_input.path.open("rb"))
        pcm = stack.enter_context(report.pcm.path.open("rb"))
        pcm.seek(58)
        for start in range(0, report.result.model_frames, 4096):
            _cancel(cancel)
            count = min(4096, report.result.model_frames - start)
            raw = model.read(count * 8)
            values = _floats(raw)
            if report.channels == 1 and any(
                values[i] != values[i + 1] for i in range(0, len(values), 2)
            ):
                raise ValueError(
                    "Mono source must be explicitly duplicated without channel changes"
                )
            if report.sample_rate == 44100:
                original = [
                    v[0] for v in struct.iter_unpack("<d", pcm.read(count * report.channels * 8))
                ]
                pairs = (
                    [(v, v) for v in original]
                    if report.channels == 1
                    else list(zip(original[::2], original[1::2], strict=True))
                )
                if b"".join(struct.pack("<ff", *p) for p in pairs) != raw:
                    raise ValueError(
                        "Model input does not preserve source samples on the same grid"
                    )


def _assembly(report: SeparationCandidate, cancel: Callable[[], bool] | None) -> None:
    frames = report.result.model_frames
    for stem_index, stem in enumerate(report.stems):
        with ExitStack() as stack:
            streams = [
                stack.enter_context(p.outputs[stem_index].file.path.open("rb"))
                for p in report.partitions
            ]
            # Check complete raw outputs, including portions outside the source extent.
            for stream in streams:
                while block := stream.read(4096 * 8):
                    _cancel(cancel)
                    _floats(block)
            model = stack.enter_context(stem.model.path.open("rb"))
            for start in range(0, frames, 4096):
                _cancel(cancel)
                count = min(4096, frames - start)
                expected: array[float] = array("f", [0.0]) * (count * 2)
                for part, stream in zip(report.partitions, streams, strict=True):
                    p = part.partition
                    low, high = (
                        max(start, p.virtual_start),
                        min(start + count, p.virtual_start + p.waveform_frames),
                    )
                    if low >= high:
                        continue
                    stream.seek((low - p.virtual_start) * 8)
                    values = _floats(stream.read((high - low) * 8))
                    offset = (low - start) * 2
                    for index, value in enumerate(values, offset):
                        expected[index] += value  # array assignment rounds each sum to float32
                if any(not math.isfinite(v) for v in expected):
                    raise ValueError("Assembled model samples overflowed float32")
                if model.read(count * 8) != _little(expected):
                    raise ValueError(
                        "Model stem differs from complete ordered partition overlap-add"
                    )


def _source_and_residual(report: SeparationCandidate, cancel: Callable[[], bool] | None) -> None:
    size = report.frames * 8
    header = struct.pack(
        "<4sI4s4sIHHIIHHH4sII4sI",
        b"RIFF",
        size + 50,
        b"WAVE",
        b"fmt ",
        18,
        3,
        2,
        report.sample_rate,
        report.sample_rate * 8,
        8,
        32,
        0,
        b"fact",
        4,
        report.frames,
        b"data",
        size,
    )
    with ExitStack() as stack:
        waves = [stack.enter_context(stem.source.path.open("rb")) for stem in report.stems]
        models = [stack.enter_context(stem.model.path.open("rb")) for stem in report.stems]
        tails = [stack.enter_context(stem.tail.path.open("rb")) for stem in report.stems]
        for stream in waves:
            if stream.read(58) != header:
                raise ValueError("Source stem WAV must retain exact float32 stereo source clock")
        for stream in tails:
            while block := stream.read(4096 * 8):
                _cancel(cancel)
                _floats(block)
        source = stack.enter_context(report.pcm.path.open("rb"))
        source.seek(58)
        residual = stack.enter_context(report.residual.path.open("rb"))
        peak = error = 0.0
        for start in range(0, report.frames, 4096):
            _cancel(cancel)
            count = min(4096, report.frames - start)
            parts = []
            for wave, model in zip(waves, models, strict=True):
                raw = wave.read(count * 8)
                parts.append(_floats(raw))
                if report.sample_rate == 44100 and model.read(count * 8) != raw:
                    raise ValueError("Same-rate source WAV samples differ from model stem")
            original = [
                v[0] for v in struct.iter_unpack("<d", source.read(count * report.channels * 8))
            ]
            retained = [v[0] for v in struct.iter_unpack("<d", residual.read(count * 16))]
            if len(retained) != count * 2 or len(original) != count * report.channels:
                raise ValueError("Complete residual/source samples are required")
            for index, value in enumerate(retained):
                expected_source = original[index // 2 if report.channels == 1 else index]
                estimates = [p[index] for p in parts]
                expected = expected_source - math.fsum(estimates)
                if not math.isfinite(value) or value != expected:
                    raise ValueError("Residual differs from source minus four complete estimates")
                peak = max(peak, abs(value))
                error = max(error, abs(math.fsum([*estimates, value]) - expected_source))
        if (peak, error) != (report.residual_peak, report.conservation_error):
            raise ValueError("Residual/conservation observations differ from complete samples")


def validate_separation_signal(
    report: SeparationCandidate, *, should_cancel: Callable[[], bool] | None = None
) -> None:
    _inputs(report, should_cancel)
    _assembly(report, should_cancel)
    _source_and_residual(report, should_cancel)
