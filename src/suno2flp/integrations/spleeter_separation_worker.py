"""Fixed source-clock separation in a private native child; no application imports."""

import hashlib
import importlib
import importlib.util
import json
import math
import struct
import sys
import time
from pathlib import Path
from typing import Any

STEMS = ("vocals", "drums", "bass", "other")
RATE = 44100
LENGTH = 4096
HOP = 1024
ROWS = 512


def wave_header(frames: int, rate: int, channels: int, bits: int) -> bytes:
    width = bits // 8
    size = frames * channels * width
    return struct.pack(
        "<4sI4s4sIHHIIHHH4sII4sI",
        b"RIFF",
        50 + size,
        b"WAVE",
        b"fmt ",
        18,
        3,
        channels,
        rate,
        rate * channels * width,
        channels * width,
        bits,
        0,
        b"fact",
        4,
        frames,
        b"data",
        size,
    )


def validate_request(request: object) -> tuple[Path, Path, int, int, int]:
    names = {"operation", "packages", "pcm", "frames", "sample_rate", "channels"}
    if not isinstance(request, dict) or set(request) != names or request["operation"] != "separate":
        raise ValueError("Unsupported separation worker operation or parameters")
    frames, rate, channels = (request[key] for key in ("frames", "sample_rate", "channels"))
    if (
        type(frames) is not int
        or type(rate) is not int
        or type(channels) is not int
        or not 8000 <= rate <= 192000
        or not 1 <= frames <= rate * 600
        or channels not in (1, 2)
        or not isinstance(request["packages"], str)
        or not isinstance(request["pcm"], str)
    ):
        raise ValueError("Unsupported complete source PCM clock or channels")
    packages, pcm = Path(request["packages"]), Path(request["pcm"])
    if not packages.is_absolute() or not pcm.is_absolute():
        raise ValueError("Native inputs require absolute fixed paths")
    if pcm.stat().st_size != 58 + frames * channels * 8:
        raise ValueError("Source PCM does not cover the complete declared samples")
    with pcm.open("rb") as stream:
        if stream.read(58) != wave_header(frames, rate, channels, 64):
            raise ValueError("Source PCM header differs from fixed float64 source geometry")
    return packages.resolve(), pcm.resolve(), frames, rate, channels


def owned_module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        f"_suno_fixed_{name}", Path(__file__).with_name(f"{name}.py")
    )
    if spec is None or spec.loader is None:
        raise ValueError("Fixed owned native helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_input(
    np: Any, signal: Any, pcm: Path, attempt: Path, frames: int, rate: int, channels: int
) -> int:
    source = np.memmap(pcm, dtype="<f8", mode="r", offset=58, shape=(frames, channels))
    try:
        for start in range(0, frames, 65536):
            if not np.isfinite(source[start : start + 65536]).all():
                raise ValueError("Complete source PCM contains nonfinite samples")
        stereo = np.repeat(source, 2, axis=1) if channels == 1 else source
        common = math.gcd(rate, RATE)
        converted = (
            stereo
            if rate == RATE
            else signal.resample_poly(
                stereo,
                RATE // common,
                rate // common,
                axis=0,
                window=("kaiser", 5.0),
                padtype="constant",
                cval=0,
            )
        )
        model = converted.astype("<f4")
        expected = (frames * RATE + rate - 1) // rate
        if model.shape != (expected, 2) or not np.isfinite(model).all():
            raise ValueError("Complete rationally resampled model input is invalid")
        with (attempt / "model-input.f32").open("xb") as stream:
            model.tofile(stream)
    finally:
        source._mmap.close()
    return expected


def zero_file(path: Path, size: int) -> None:
    with path.open("xb") as stream:
        stream.seek(size - 1)
        stream.write(b"\0")


def infer_partitions(helper: Any, packages: Path, attempt: Path, frames: int) -> dict[str, Any]:
    np, session, waveform, outputs, proof = helper.native(packages, attempt, partitioned=True)
    source = np.memmap(attempt / "model-input.f32", dtype="<f4", mode="r", shape=(frames, 2))
    maps = {}
    partials = []
    parts = attempt / "parts"
    parts.mkdir()
    try:
        for name in STEMS:
            path = attempt / f"model.{name}.f32"
            zero_file(path, frames * 8)
            maps[name] = np.memmap(path, dtype="<f4", mode="r+", shape=(frames, 2))
        total_rows = (frames + LENGTH + HOP - 1) // HOP
        for index, start in enumerate(range(0, total_rows, ROWS)):
            rows = min(ROWS, total_rows - start)
            virtual_start = start * HOP - LENGTH
            count = (rows - 1) * HOP + LENGTH
            block = np.zeros((count, 2), dtype="<f4")
            low, high = max(0, virtual_start), min(frames, virtual_start + count)
            block[low - virtual_start : high - virtual_start] = source[low:high]
            input_path = parts / f"{index:04d}.input.f32"
            with input_path.open("xb") as stream:
                block.tofile(stream)
            predicted = helper.predict(np, session, waveform, outputs, block)
            hashes = {}
            for name in STEMS:
                path = parts / f"{index:04d}.{name}.f32"
                with path.open("xb") as stream:
                    predicted[name].astype("<f4", copy=False).tofile(stream)
                maps[name][low:high] += predicted[name][low - virtual_start : high - virtual_start]
                hashes[name] = digest(path)
            partials.append(
                dict(
                    partition=dict(
                        index=index,
                        stft_start=start,
                        stft_frames=rows,
                        virtual_start=virtual_start,
                        waveform_frames=count,
                    ),
                    input_sha256=digest(input_path),
                    output_sha256=hashes,
                )
            )
    finally:
        source._mmap.close()
        for output in maps.values():
            output.flush()
            output._mmap.close()
        session.close()
    return dict(
        execution={
            key: value
            for key, value in proof.items()
            if key not in ("profile", "fixtures", "repeatability_scope")
        },
        partitions=partials,
        model_output_sha256={name: digest(attempt / f"model.{name}.f32") for name in STEMS},
    )


def source_outputs(
    np: Any, signal: Any, attempt: Path, frames: int, rate: int, model_frames: int
) -> dict[str, Any]:
    common = math.gcd(rate, RATE)
    expected = (model_frames * rate + RATE - 1) // RATE
    wav_hashes, tail_hashes = {}, {}
    for name in STEMS:
        model = np.memmap(
            attempt / f"model.{name}.f32", dtype="<f4", mode="r", shape=(model_frames, 2)
        )
        try:
            returned = (
                model
                if rate == RATE
                else signal.resample_poly(
                    model,
                    rate // common,
                    RATE // common,
                    axis=0,
                    window=("kaiser", 5.0),
                    padtype="constant",
                    cval=0,
                )
            )
            if returned.shape != (expected, 2) or not np.isfinite(returned).all():
                raise ValueError("Complete source-grid resampling is invalid")
            wav = attempt / f"{name}.wav"
            with wav.open("xb") as stream:
                stream.write(wave_header(frames, rate, 2, 32))
                stream.flush()
                returned[:frames].astype("<f4", copy=False).tofile(stream)
            tail = attempt / f"{name}.tail.f32"
            with tail.open("xb") as stream:
                returned[frames:].astype("<f4", copy=False).tofile(stream)
            wav_hashes[name], tail_hashes[name] = digest(wav), digest(tail)
            del returned
        finally:
            model._mmap.close()
    return dict(
        returned_source_frames=expected,
        source_output_sha256=wav_hashes,
        resampling_tail_sha256=tail_hashes,
    )


def main() -> None:
    started = time.perf_counter()
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    packages, pcm, frames, rate, channels = validate_request(request)
    attempt = request_path.parent
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("Worker requires -I -S -B")
    helper = owned_module("spleeter_worker")
    helper.isolate_environment(packages, attempt)
    sys.path.insert(0, str(packages))
    np = importlib.import_module("numpy")
    signal = importlib.import_module("scipy.signal")
    model_frames = prepare_input(np, signal, pcm, attempt, frames, rate, channels)
    result = infer_partitions(helper, packages, attempt, model_frames)
    result.update(source_outputs(np, signal, attempt, frames, rate, model_frames))
    working_set, commit = owned_module("process_metrics").peak_process_memory()
    result.update(
        profile="global-stft-four-stem-result-v1",
        source_frames=frames,
        sample_rate=rate,
        source_channels=channels,
        model_frames=model_frames,
        model_input_sha256=digest(attempt / "model-input.f32"),
        peak_working_set_bytes=working_set,
        peak_commit_bytes=commit,
        elapsed_seconds=time.perf_counter() - started,
    )
    with (attempt / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
