"""Isolated private CPU inference. No upstream loaders, network or ambient site."""

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import socket
import sys
import time
from pathlib import Path


def main() -> None:
    worker_started = time.monotonic()
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise ValueError("Rhythm worker requires -I -S -B")
    request_path = Path(sys.argv[1]).resolve(strict=True)
    attempt = request_path.parent
    request = json.loads(request_path.read_bytes())
    if set(request) != {"packages", "pins", "pcm", "frames", "sample_rate", "channels"}:
        raise ValueError("Unknown rhythm worker request")
    packages = Path(request["packages"]).resolve(strict=True)
    os.environ.update(
        CUDA_VISIBLE_DEVICES="-1",
        OMP_NUM_THREADS="8",
        MKL_NUM_THREADS="8",
        OPENBLAS_NUM_THREADS="8",
        NUMEXPR_NUM_THREADS="8",
        TORCHDYNAMO_DISABLE="1",
        TORCH_HOME=str(attempt / "cache/torch"),
        TORCHINDUCTOR_CACHE_DIR=str(attempt / "cache/inductor"),
        XDG_CACHE_HOME=str(attempt / "cache/xdg"),
    )

    def no_network(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Network and upstream download fallback are disabled")

    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network  # type: ignore[assignment]
    sys.path.insert(0, str(packages))
    import numpy as np  # type: ignore[import-not-found]
    import soxr  # type: ignore[import-not-found]
    import torch  # type: ignore[import-not-found]

    torch.hub.load_state_dict_from_url = no_network
    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.mkldnn.enabled = False
    torch.set_float32_matmul_precision("highest")
    torch.set_flush_denormal(False)
    torch.manual_seed(3)
    if torch.version.cuda is not None:
        raise ValueError("A CPU-only Torch build is required")
    pins = json.loads(Path(request["pins"]).read_bytes())
    model_path = packages / "models/final0.ckpt"
    with model_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != pins["model"]["sha256"]:
            raise ValueError("Fixed local checkpoint is missing or corrupt")
    if torch.serialization.get_unsafe_globals_in_checkpoint(model_path):
        raise ValueError("Checkpoint has unsupported pickle globals")
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    from beat_this.inference import aggregate_prediction, split_piece  # type: ignore[import-not-found]
    from beat_this.model.beat_tracker import BeatThis  # type: ignore[import-not-found]
    from beat_this.model.postprocessor import Postprocessor  # type: ignore[import-not-found]
    from beat_this.preprocessing import LogMelSpect  # type: ignore[import-not-found]
    from beat_this.utils import replace_state_dict_key  # type: ignore[import-not-found]

    hparams = dict(
        spect_dim=128,
        transformer_dim=512,
        ff_mult=4,
        n_layers=6,
        stem_dim=32,
        dropout={"frontend": 0.1, "transformer": 0.2},
        head_dim=32,
    )
    if any(checkpoint["hyper_parameters"].get(k) != v for k, v in hparams.items()):
        raise ValueError("Fixed checkpoint architecture changed")
    model = BeatThis(**hparams).to("cpu").eval()
    model.load_state_dict(
        replace_state_dict_key(checkpoint["state_dict"], "model.", ""), strict=True
    )
    state_digest, geometry = hashlib.sha256(), {}
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        geometry[name] = dict(shape=list(array.shape), dtype=str(array.dtype))
        state_digest.update(
            name.encode()
            + b"\0"
            + str(array.shape).encode()
            + b"\0"
            + str(array.dtype).encode()
            + b"\0"
        )
        state_digest.update(array.tobytes())
    if geometry != pins["model_geometry"] or state_digest.hexdigest() != pins["model_state_sha256"]:
        raise ValueError("Restored checkpoint tensors differ from the audited recipe")
    frames, rate, channels = (request[k] for k in ("frames", "sample_rate", "channels"))
    if any(type(v) is not int for v in (frames, rate, channels)) or not (
        8000 <= rate <= 192000 and 1 <= frames <= rate * 600 and channels in (1, 2)
    ):
        raise ValueError("Unsupported original PCM geometry")
    pcm_path = Path(request["pcm"]).resolve(strict=True)
    if pcm_path.stat().st_size != 58 + frames * channels * 8:
        raise ValueError("Source PCM size disagrees with its complete geometry")
    source = np.memmap(pcm_path, dtype="<f8", mode="r", offset=58, shape=(frames, channels))
    if not np.isfinite(source).all() or np.max(np.abs(source)) > 1:
        raise ValueError("Expected complete finite normalized original PCM")
    mono = np.mean(source, axis=1, dtype=np.float64)
    resampled = soxr.resample(mono, rate, 22050, quality="HQ") if rate != 22050 else mono.copy()
    if len(resampled) <= 512:
        raise ValueError("Audio is too short for the fixed reflect-padded frontend")
    wave = torch.tensor(resampled, dtype=torch.float32)
    files = {}

    def save(name: str, array: object, encoding: str) -> None:
        values = np.asarray(array, dtype=encoding)
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite native rhythm output")
        data = values.tobytes()
        with (attempt / name).open("xb") as stream:
            stream.write(data)
        files[name] = dict(
            shape=list(values.shape),
            encoding=encoding,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    started = time.monotonic()
    save("mono.f64", mono, "<f8")
    save("resampled.f64", resampled, "<f8")
    save("wave.f32", wave.numpy(), "<f4")
    with torch.inference_mode():
        spect = LogMelSpect(device="cpu")(wave)
        save("spect.f32", spect.numpy(), "<f4")
        chunks, starts = split_piece(spect, 1500, border_size=6, avoid_short_end=True)
        predictions = []
        for i, chunk in enumerate(chunks):
            save(f"chunk-{i}-input.f32", chunk.numpy(), "<f4")
            pred = {
                k: v[0] for k, v in model(chunk.unsqueeze(0)).items() if k in ("beat", "downbeat")
            }
            for name, values in pred.items():
                save(f"chunk-{i}-{name}.f32", values.numpy(), "<f4")
            predictions.append(pred)
        beat, downbeat = aggregate_prediction(
            predictions, starts, len(spect), 1500, 6, "keep_first", "cpu"
        )
        save("beat.f32", beat.numpy(), "<f4")
        save("downbeat.f32", downbeat.numpy(), "<f4")
        beats, downbeats = Postprocessor(type="minimal", fps=50)(beat, downbeat)
        save("beats.f64", beats, "<f8")
        save("downbeats.f64", downbeats, "<f8")
    versions = {
        p["distribution"]: importlib.metadata.version(p["distribution"]) for p in pins["artifacts"]
    }
    if versions != {p["distribution"]: p["version"] for p in pins["artifacts"]}:
        raise ValueError("Actual installed versions differ from fixed wheel metadata")
    modules = {
        name: str(Path(str(importlib.import_module(name).__file__)).resolve())
        for name in (
            "torch",
            "torchaudio",
            "numpy",
            "soxr",
            "beat_this",
            "einops",
            "rotary_embedding_torch",
        )
    }
    if any(not Path(p).is_relative_to(packages) for p in modules.values()):
        raise ValueError("Native module escaped the private payload")
    spec = importlib.util.spec_from_file_location(
        "beat_process_metrics", Path(__file__).with_name("process_metrics.py")
    )
    if spec is None or spec.loader is None:
        raise ValueError("Native process memory observer is unavailable")
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    working_set, commit = observer.peak_process_memory()
    if max(working_set, commit) > 16 * 1024**3:
        raise ValueError("Native beat process exceeded the16GiB memory budget")
    result = dict(
        execution=dict(
            profile="beat-this-final0-fixed-cpu-v1",
            intra_op_threads=torch.get_num_threads(),
            inter_op_threads=torch.get_num_interop_threads(),
            deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),
            mkldnn=torch.backends.mkldnn.enabled,
            cuda=torch.version.cuda,
            matmul_precision=torch.get_float32_matmul_precision(),
            model_state_sha256=state_digest.hexdigest(),
            geometry=geometry,
            versions=versions,
            modules=modules,
        ),
        frames=frames,
        sample_rate=rate,
        channels=channels,
        chunk_starts=[int(s) for s in starts],
        files=files,
        source_peak=float(np.max(np.abs(source))),
        mono_peak=float(np.max(np.abs(mono))),
        inference_seconds=time.monotonic() - started,
        worker_seconds=time.monotonic() - worker_started,
        peak_working_set=working_set,
        peak_commit=commit,
    )
    with (attempt / "result.json").open("x", encoding="utf-8") as result_stream:
        json.dump(result, result_stream, allow_nan=False, indent=2)


if __name__ == "__main__":
    main()
