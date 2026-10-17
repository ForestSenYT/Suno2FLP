"""Fixed private encoder-only CPU worker; no core imports or upstream loaders."""

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import socket
import sys
import time
from pathlib import Path


def main() -> None:
    started = time.monotonic()
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise ValueError("Drum worker requires -I -S -B")
    request_path = Path(sys.argv[1]).resolve(strict=True)
    attempt = request_path.parent
    if request_path.stat().st_size > 65536:
        raise ValueError("Drum request exceeds budget")
    request = json.loads(request_path.read_bytes())
    if set(request) != {"packages", "pins", "pcm", "model_frames"}:
        raise ValueError("Unexpected drum request keys")
    frames = request["model_frames"]
    if type(frames) is not int or not 513 <= frames <= 26460000:
        raise ValueError("Unsupported complete drum input geometry")
    packages = Path(request["packages"]).resolve(strict=True)
    pins = json.loads(Path(request["pins"]).read_bytes())
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
        raise RuntimeError("Drum network and upstream download fallback are disabled")

    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network  # type: ignore[assignment]
    sys.path.insert(0, str(packages))
    import einops  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]
    import torch  # type: ignore[import-not-found]
    import torchaudio  # type: ignore[import-not-found]

    torch.hub.load_state_dict_from_url = no_network
    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.mkldnn.enabled = False
    torch.set_float32_matmul_precision("highest")
    torch.set_flush_denormal(False)
    torch.manual_seed(3)
    if torch.version.cuda is not None:
        raise ValueError("Drum profile requires CPU-only Torch")
    checkpoint_path = packages / "models/idm.ckpt"
    with checkpoint_path.open("rb") as checkpoint_stream:
        checkpoint_sha256 = hashlib.file_digest(checkpoint_stream, "sha256").hexdigest()
    if checkpoint_sha256 != pins["checkpoint_sha256"]:
        raise ValueError("Fixed drum checkpoint changed")
    if torch.serialization.get_unsafe_globals_in_checkpoint(checkpoint_path):
        raise ValueError("Drum checkpoint has unsupported pickle globals")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if set(checkpoint) != {"epoch", "global_step", "state_dict"}:
        raise ValueError("Unexpected drum checkpoint container")
    state = checkpoint["state_dict"]
    geometry = {}
    for name, tensor in state.items():
        if not isinstance(name, str) or not isinstance(tensor, torch.Tensor):
            raise ValueError("Non-tensor drum checkpoint entry")
        if tensor.dtype != torch.float32 or not torch.isfinite(tensor).all():
            raise ValueError("Unsupported dtype/nonfinite drum state")
        geometry[name] = dict(shape=list(tensor.shape), dtype="float32")
    if geometry != pins["state"]:
        raise ValueError("Complete drum checkpoint state differs from fixed geometry")

    from idm.feature_extractor.convnext import ConvNeXt  # type: ignore[import-not-found]
    from idm.feature_extractor.encoder import Encoder  # type: ignore[import-not-found]
    from idm.feature_extractor.mel import MelSpectrogram  # type: ignore[import-not-found]
    from idm.synthesis_conditioning.embedding import DrumKitClassifier  # type: ignore[import-not-found]
    from idm.synthesis_conditioning.transcription import TranscriptionHead  # type: ignore[import-not-found]

    model = Encoder(
        backbone=ConvNeXt(
            dims=[4, 8, 16, 32], downsample=False, input_channels=1, kernel_size=7, drop_path_rate=0
        ),
        pooling=DrumKitClassifier(in_features=32, n_drum_kits=6),
        transcription_head=TranscriptionHead(
            input_dim=32,
            n_classes=9,
            kernel_size=7,
            sequence_model=torch.nn.Identity(),
            activation="relu",
            onset_activation="none",
            velocity_activation="exp_sigmoid",
        ),
        transform=MelSpectrogram(
            sample_rate=44100, n_fft=1024, n_mels=128, hop_length=256, log=True
        ),
        sampling_rate=44100,
        embedding_norm=torch.nn.Softmax(dim=-1),
    ).eval()
    encoder = {k.removeprefix("encoder."): v for k, v in state.items() if k.startswith("encoder.")}
    expected_state = model.state_dict()
    if len(encoder) != 194 or set(encoder) != set(expected_state):
        raise ValueError("Complete drum encoder key set changed")
    for name, value in expected_state.items():
        if value.shape != encoder[name].shape or value.dtype != encoder[name].dtype:
            raise ValueError("Drum encoder tensor shape/dtype mismatch")
    model.load_state_dict(encoder, strict=True)
    convolutions = []
    for layer in model.backbone.downsample_layers:
        conv = layer[0] if isinstance(layer[0], torch.nn.Conv2d) else layer[1]
        convolutions.append(
            [conv.kernel_size[-1], conv.padding[-1], conv.stride[-1], conv.dilation[-1]]
        )
    if convolutions != [[7, 3, 1, 1], [3, 3, 1, 1], [3, 3, 1, 1], [3, 3, 1, 1]]:
        raise ValueError("Drum time convolution origin/support changed")

    pcm = request["pcm"]
    if set(pcm) != {"path", "sha256", "size_bytes", "mtime_ns"}:
        raise ValueError("Unexpected drum source identity")
    source = Path(pcm["path"]).resolve(strict=True)

    def verify_source() -> None:
        before = source.stat()
        if before.st_size != frames * 8 or (before.st_size, before.st_mtime_ns) != (
            pcm["size_bytes"],
            pcm["mtime_ns"],
        ):
            raise ValueError("Complete stereo float32 drum source geometry changed")
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = source.stat()
        if digest != pcm["sha256"] or (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
        ):
            raise ValueError("Drum source bytes changed")

    verify_source()
    audio = np.fromfile(source, dtype="<f4").reshape(frames, 2)
    if not np.isfinite(audio).all():
        raise ValueError("Nonfinite drum model input")
    # Explicit pairwise float64 sum/half -> float32; no reduction, clipping or normalization.
    mono = ((audio[:, 0].astype(np.float64) + audio[:, 1].astype(np.float64)) * 0.5).astype("<f4")
    if not np.isfinite(mono).all():
        raise ValueError("Nonfinite drum mono conversion")
    inference_started = time.monotonic()
    with torch.inference_mode():
        output = model(torch.from_numpy(mono).unsqueeze(0))["activations"]
    inference_seconds = time.monotonic() - inference_started
    rows = (frames + 255) // 256 + 13
    arrays = {"mono.f32": mono}
    for key, filename in (("onset", "onsets.f32"), ("velocity", "velocities.f32")):
        value = output[key].detach().cpu().numpy()
        if value.shape != (1, 9, rows) or value.dtype != np.float32 or not np.isfinite(value).all():
            raise ValueError("Incomplete/nonfinite drum encoder output")
        arrays[filename] = np.ascontiguousarray(value[0], dtype="<f4")
    files = {}
    for filename, value in arrays.items():
        raw = value.tobytes(order="C")
        with (attempt / filename).open("xb") as array_stream:
            array_stream.write(raw)
        files[filename] = dict(
            shape=list(value.shape),
            encoding="<f4",
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    verify_source()
    spec = importlib.util.spec_from_file_location(
        "drum_process_metrics", Path(__file__).with_name("process_metrics.py")
    )
    assert spec is not None and spec.loader is not None
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    working, commit = metrics.peak_process_memory()
    if max(working, commit) > 16 * 1024**3:
        raise ValueError("Observed drum worker memory exceeds16GiB")
    result = dict(
        profile="complete-idm-encoder-output-v1",
        model_frames=frames,
        sample_rate=44100,
        channels=2,
        rows=rows,
        classes=pins["classes"],
        source_sha256=pcm["sha256"],
        files=files,
        source_peak=float(np.abs(audio).max()),
        mono_peak=float(np.abs(mono).max()),
        inference_seconds=inference_seconds,
        worker_seconds=time.monotonic() - started,
        peak_working_set=working,
        peak_commit=commit,
        execution=dict(
            profile="idm-encoder-only-fixed-cpu-v1",
            intra_op_threads=torch.get_num_threads(),
            inter_op_threads=torch.get_num_interop_threads(),
            deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),
            mkldnn=torch.backends.mkldnn.enabled,
            cuda=torch.version.cuda,
            matmul_precision=torch.get_float32_matmul_precision(),
            checkpoint_sha256=checkpoint_sha256,
            geometry=geometry,
            time_convolutions=convolutions,
            versions={
                p["distribution"]: importlib.metadata.version(p["distribution"])
                for p in pins["artifacts"]
            },
            modules={
                m.__name__: m.__file__ for m in (torch, torchaudio, np, einops, sys.modules["idm"])
            },
        ),
    )
    with (attempt / "result.json").open("x", encoding="utf-8") as result_stream:
        json.dump(result, result_stream, allow_nan=False, indent=2)
    print(json.dumps(dict(rows=rows, classes=9, strict_encoder_tensors=len(encoder))))


if __name__ == "__main__":
    main()
