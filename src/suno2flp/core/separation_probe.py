"""Original probe signals and independent numeric readback, without native packages."""

import math
import struct
from pathlib import Path

from suno2flp.core.offline_files import capture_input, capture_stream_input, guarded_path
from suno2flp.core.separation_runtime import (
    PROBE_FRAMES,
    STEMS,
    SeparationFixtureResult,
    SeparationSignalEvidence,
)


def fixture_bytes(fixture: str) -> bytes:
    count = PROBE_FRAMES[fixture]
    raw = bytearray(count * 8)
    if fixture == "impulses":
        for frame, channel, value in ((0, 0, 0.5), (6000, 0, 0.25), (12346, 1, 0.75)):
            struct.pack_into("<f", raw, frame * 8 + channel * 4, value)
    elif fixture == "stereo-pattern":
        for frame in range(count):
            struct.pack_into(
                "<ff",
                raw,
                frame * 8,
                ((frame * 37) % 1024 - 512) / 2048,
                ((frame * 71 + 19) % 2048 - 1024) / 4096,
            )
    return bytes(raw)


def check_fixture(attempt: Path, result: SeparationFixtureResult) -> SeparationSignalEvidence:
    result = SeparationFixtureResult.model_validate(result.model_dump())
    fixture = result.fixture
    source, raw = capture_input(attempt / f"{fixture}.input.f32")
    if raw != fixture_bytes(fixture):
        raise ValueError("Native probe source differs from the fixed original fixture")
    source_values = [value[0] for value in struct.iter_unpack("<f", raw)]
    arrays: list[list[float]] = []
    outputs = []
    for name in STEMS:
        for run in (1, 2):
            path = guarded_path(attempt / f"{fixture}.{name}.{run}.f32")
            if path.stat().st_size != result.frames * 8:
                raise ValueError("Native output does not retain every stereo source frame")
            identity, raw = capture_input(path)
            if identity.sha256 != result.hashes[name][run - 1]:
                raise ValueError("Native repeated output disagrees with recorded bytes")
            values = [value[0] for value in struct.iter_unpack("<f", raw)]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Native output has nonfinite samples")
            outputs.append(identity)
            if run == 1:
                arrays.append(values)
    mixed = [math.fsum(values) for values in zip(*arrays, strict=True)]
    if fixture == "silence":
        if any(value for values in arrays for value in values):
            raise ValueError("Native silence probe unexpectedly produced nonzero output")
    elif not any(mixed) or len({result.hashes[name][0] for name in STEMS}) == 1:
        raise ValueError("Nonzero model probe produced trivial or identical stems")
    peaks = None
    if fixture == "impulses":
        regions = ((0, 0, 2048, 0), (0, 3952, 8049, 6000), (1, 10299, 12347, 12346))
        peaks = []
        for channel, start, stop, expected in regions:
            peak = max(range(start, stop), key=lambda frame: abs(mixed[frame * 2 + channel]))
            if abs(peak - expected) > 1:
                raise ValueError("Native impulse origin moved by more than one decoded sample")
            peaks.append(peak)
    residual = [value - estimated for value, estimated in zip(source_values, mixed, strict=True)]
    error = max(
        abs(value - math.fsum((*stems, remaining)))
        for value, stems, remaining in zip(
            source_values, zip(*arrays, strict=True), residual, strict=True
        )
    )
    if error > 1e-12 or not all(math.isfinite(value) for value in residual):
        raise ValueError("Native residual does not conserve the authored signal")
    path = guarded_path(attempt / f"{fixture}.unassigned-residual.f64")
    with path.open("xb") as stream:
        for value in residual:
            stream.write(struct.pack("<d", value))
    return SeparationSignalEvidence(
        fixture=fixture,
        source=source,
        outputs=outputs,
        residual=capture_stream_input(path),
        residual_peak=max(abs(value) for value in residual),
        conservation_error=error,
        impulse_peak_frames=peaks,
    )
