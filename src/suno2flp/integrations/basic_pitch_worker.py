"""Standalone audited CPU worker; native dependencies never enter the application runtime."""

import importlib
import importlib.metadata
import json
import math
import os
import platform
import sys
import sysconfig
from contextlib import ExitStack
from pathlib import Path
from typing import Any

OUTPUTS = {
    "note": ("StatefulPartitionedCall:1", 88),
    "onset": ("StatefulPartitionedCall:2", 88),
    "contour": ("StatefulPartitionedCall:0", 264),
}


def native(packages: Path, attempt: Path) -> tuple[Any, Any, Any, dict[str, Any]]:
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("Worker requires -I -S -B")
    if (
        sys.platform != "win32"
        or sysconfig.get_platform() != "win-amd64"
        or platform.python_version() != "3.11.16"
    ):
        raise ValueError("Worker requires fixed Windows x64 CPython3.11.16")
    cache = attempt / "cache"
    cache.mkdir(exist_ok=False)
    os.environ.update(
        NUMBA_CACHE_DIR=str(cache / "numba"),
        JOBLIB_TEMP_FOLDER=str(cache / "joblib"),
        MPLCONFIGDIR=str(cache / "matplotlib"),
    )
    sys.path.insert(0, str(packages))
    np = importlib.import_module("numpy")
    ort = importlib.import_module("onnxruntime")
    notes = importlib.import_module("basic_pitch.note_creation")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 8
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.use_deterministic_compute = True
    session = ort.InferenceSession(
        str(packages / "basic_pitch/saved_models/icassp_2022/nmp.onnx"),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    if session.get_providers() != ["CPUExecutionProvider"]:
        raise ValueError("Unexpected execution provider")
    versions = {
        name: importlib.metadata.version(name)
        for name in ("onnxruntime", "numpy", "scipy", "basic-pitch")
    }
    modules = {}
    for name in (
        "numpy",
        "onnxruntime",
        "scipy",
        "basic_pitch",
        "librosa",
        "pretty_midi",
        "mir_eval",
        "resampy",
    ):
        module = importlib.import_module(name)
        assert module.__file__ is not None
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(packages):
            raise ValueError("Package imported outside isolated payload")
        modules[name] = str(path)
    probe = {
        "profile": "basic-pitch-native-probe-v1",
        "provider": session.get_providers()[0],
        "intra_op_threads": session.get_session_options().intra_op_num_threads,
        "inter_op_threads": session.get_session_options().inter_op_num_threads,
        "sequential": session.get_session_options().execution_mode
        == ort.ExecutionMode.ORT_SEQUENTIAL,
        "versions": versions,
        "modules": modules,
    }
    return np, session, notes, probe


def predict(np: Any, session: Any, audio: Any) -> dict[str, Any]:
    outputs = session.run(
        [value[0] for value in OUTPUTS.values()],
        {"serving_default_input_2:0": audio.reshape(1, 43844, 1)},
    )
    result = dict(zip(OUTPUTS, outputs, strict=True))
    for name, array in result.items():
        if (
            array.shape != (1, 172, OUTPUTS[name][1])
            or array.dtype != np.float32
            or not np.all(np.isfinite(array))
            or np.any(array < 0)
            or np.any(array > 1)
        ):
            raise ValueError("Model output shape/dtype/range disagrees with fixed profile")
    return result


def transcribe(
    np: Any, session: Any, notes: Any, request: dict[str, Any], attempt: Path, probe: dict[str, Any]
) -> dict[str, Any]:
    frames, rate, channels = (request[k] for k in ("frames", "sample_rate", "channels"))
    if (
        any(type(n) is not int for n in (frames, rate, channels))
        or not 8000 <= rate <= 192000
        or not 0 < frames <= 600 * rate
        or channels not in (1, 2)
    ):
        raise ValueError("Source clock exceeds fixed inference profile")
    source = Path(request["pcm"])
    if source.stat().st_size != 58 + frames * channels * 8:
        raise ValueError("Decoded PCM must cover all original source frames")
    pcm = np.memmap(source, dtype="<f8", mode="r", offset=58, shape=(frames, channels))
    mono = np.empty(frames, dtype=np.float32)
    for start in range(0, frames, 1_000_000):
        stop = min(frames, start + 1_000_000)
        block = np.mean(pcm[start:stop], axis=1, dtype=np.float64)
        if not np.all(np.isfinite(block)):
            raise ValueError("Decoded waveform has nonfinite samples")
        mono[start:stop] = block
    signal = importlib.import_module("scipy.signal")
    divisor = math.gcd(rate, 22050)
    mono = signal.resample_poly(
        mono,
        22050 // divisor,
        rate // divisor,
        window=("kaiser", 5.0),
        padtype="constant",
        cval=0.0,
    ).astype("<f4", copy=False)
    count = (frames * 22050 + rate - 1) // rate
    if len(mono) != count or not np.all(np.isfinite(mono)):
        raise ValueError("Resampler did not retain the complete derived sample clock")
    with (attempt / "mono.f32").open("xb") as stream:
        mono.tofile(stream)
    # Upstream schedules starts on the virtually left-padded source, including a
    # possible final padding-only ownership window. Every raw row remains saved.
    windows = [start - 3840 for start in range(0, count + 3840, 36164)]
    owned: dict[str, list[Any]] = {name: [] for name in OUTPUTS}
    with ExitStack() as stack:
        streams = {
            name: stack.enter_context((attempt / f"{name}.f32").open("xb")) for name in OUTPUTS
        }
        for start in windows:
            audio = np.zeros(43844, dtype=np.float32)
            left, right = max(0, start), min(count, start + 43844)
            if right > left:
                audio[left - start : right - start] = mono[left:right]
            output = predict(np, session, audio)
            rows = [row for row in range(15, 157) if 0 <= start + row * 256 < count]
            for name, array in output.items():
                array.astype("<f4", copy=False).tofile(streams[name])
                if rows:
                    owned[name].append(array[0, rows].copy())
    dense = {name: np.concatenate(values, axis=0) for name, values in owned.items()}
    events = notes.output_to_notes_polyphonic(
        dense["note"].copy(),
        dense["onset"].copy(),
        onset_thresh=0.5,
        frame_thresh=0.3,
        min_note_len=11,
        infer_onsets=True,
        max_freq=None,
        min_freq=None,
        melodia_trick=True,
        energy_tol=11,
    )
    if len(events) > 10000:
        raise ValueError("Complete inferred note count exceeds 10000; no truncation allowed")
    result = []
    offset = 0
    with (attempt / "bends.i8").open("xb") as stream:
        # Per-note extraction bounds transient memory and preserves overlapping bends.
        for event in events:
            start, end, pitch, activation, bends = notes.get_pitch_bends(
                dense["contour"], [event], n_bins_tolerance=25
            )[0]
            if (
                bends is None
                or len(bends) != end - start
                or any(not -25 <= int(v) <= 25 for v in bends)
            ):
                raise ValueError("Incomplete or invalid per-note bend evidence")
            if offset + len(bends) > 64 * 1024**2:
                raise ValueError("Complete bend evidence exceeds budget")
            np.asarray(bends, dtype=np.int8).tofile(stream)
            result.append(
                {
                    "start_frame": int(start),
                    "end_frame": int(end),
                    "pitch": int(pitch),
                    "activation": float(activation),
                    "bend_offset": offset,
                }
            )
            offset += len(bends)
    return {
        "profile": "basic-pitch-frame-estimates-v1",
        "probe": probe,
        "resampled_frames": count,
        "windows": len(windows),
        "owned_rows": len(dense["note"]),
        "notes": result,
        "bend_bytes": offset,
    }


def main() -> None:
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    attempt = request_path.parent
    np, session, notes, probe = native(Path(request["packages"]).resolve(), attempt)
    audio = np.zeros(43844, dtype=np.float32)
    first = predict(np, session, audio)
    second = predict(np, session, audio)
    if any(not np.array_equal(first[name], second[name]) for name in OUTPUTS):
        raise ValueError("Repeated native inference is not bit repeatable")
    probe.update(shapes={k: list(v.shape) for k, v in first.items()}, repeatable=True)
    if request["operation"] == "probe":
        result = probe
    elif request["operation"] == "transcribe":
        result = transcribe(np, session, notes, request, attempt, probe)
    else:
        raise ValueError("Unsupported worker operation")
    with (attempt / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, allow_nan=False, indent=2)


if __name__ == "__main__":
    main()
