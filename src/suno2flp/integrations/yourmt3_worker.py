"""Fixed isolated CPU inference/token replay; never import the author demo."""

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import socket
import sys
import time
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def write_window_evidence(root: Path, window: dict[str, Any]) -> None:
    index = window["index"]
    if type(index) is not int or not 0 <= index <= 292:
        raise ValueError("Invalid native window journal address")
    with (root / f"window-{index:03}.json").open("x", encoding="utf-8") as output:
        json.dump(window, output, indent=2, allow_nan=False)


def configurations_match(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(
        expected, sort_keys=True, allow_nan=False
    )


def configure_environment(attempt: Path) -> None:
    os.environ.update(
        CUDA_VISIBLE_DEVICES="-1",
        OMP_NUM_THREADS="8",
        MKL_NUM_THREADS="8",
        OPENBLAS_NUM_THREADS="8",
        NUMEXPR_NUM_THREADS="8",
        WANDB_MODE="disabled",
        WANDB_SILENT="true",
        WANDB_ERROR_REPORTING="false",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        DO_NOT_TRACK="1",
        TOKENIZERS_PARALLELISM="false",
        TORCHDYNAMO_DISABLE="1",
        TORCHINDUCTOR_CACHE_DIR=str(attempt / "cache/inductor"),
        HF_HOME=str(attempt / "cache/hf"),
        TRANSFORMERS_CACHE=str(attempt / "cache/transformers"),
        TORCH_HOME=str(attempt / "cache/torch"),
        XDG_CACHE_HOME=str(attempt / "cache/xdg"),
        TEMP=str(attempt / "tmp"),
        TMP=str(attempt / "tmp"),
    )


def main() -> None:
    started = time.monotonic()
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise ValueError("YourMT3 worker requires -I -S -B")
    path = Path(sys.argv[1]).resolve(strict=True)
    if path.stat().st_size > 65536:
        raise ValueError("YourMT3 request exceeds budget")
    request = json.loads(path.read_bytes())
    if set(request) != {
        "mode",
        "packages",
        "pins",
        "pcm",
        "frames",
        "sample_rate",
        "channels",
        "raw",
    }:
        raise ValueError("Unexpected YourMT3 request fields")
    mode = request["mode"]
    if mode not in ("infer", "decode"):
        raise ValueError("Unsupported fixed worker operation")
    frames, rate, channels = (request[k] for k in ("frames", "sample_rate", "channels"))
    if (
        type(frames) is not int
        or type(rate) is not int
        or type(channels) is not int
        or not 8000 <= rate <= 192000
        or not 0 < frames <= rate * 600
        or channels not in (1, 2)
    ):
        raise ValueError("Unsupported complete source geometry")
    attempt = path.parent
    (attempt / "tmp").mkdir()
    configure_environment(attempt)

    def no_network(*args: object, **kwargs: object) -> Any:
        raise RuntimeError("YourMT3 network and download fallback are disabled")

    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.socket.connect_ex = no_network  # type: ignore[method-assign]
    socket.socket.sendto = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network
    packages = Path(request["packages"]).resolve(strict=True)
    pins = json.loads(Path(request["pins"]).read_bytes())
    sys.path[:0] = [str(packages), str(packages / "upstream")]
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
        raise ValueError("YourMT3 fixed profile requires CPU-only Torch")
    versions = {
        p["distribution"]: importlib.metadata.version(p["distribution"]) for p in pins["wheels"]
    }
    if versions != {p["distribution"]: p["version"] for p in pins["wheels"]}:
        raise ValueError("YourMT3 installed versions disagree with fixed wheels")

    from utils.task_manager import TaskManager  # type: ignore[import-not-found]

    tm = TaskManager(task_name="mt3_full_plus", max_shift_steps=206)
    count = (frames * 16000 + rate - 1) // rate
    windows: list[dict[str, Any]] = []
    if mode == "infer":
        checkpoint = packages / "models/model.ckpt"
        pin = next(p for p in pins["files"] if p["target"] == "models/model.ckpt")
        with checkpoint.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if checkpoint.stat().st_size != pin["size_bytes"] or digest != pin["sha256"]:
            raise ValueError("Fixed YourMT3 checkpoint changed")
        from utils.event_codec import FastCodec  # type: ignore[import-not-found]
        from utils.note_event_dataclasses import Event, EventRange  # type: ignore[import-not-found]
        from utils.tokenizer import NoteEventTokenizer  # type: ignore[import-not-found]

        allowed = [
            TaskManager,
            NoteEventTokenizer,
            EventRange,
            Event,
            FastCodec,
            np.core.multiarray.scalar,
            np.core.multiarray._reconstruct,
            np.ndarray,
            np.dtype,
            np.dtypes.Float64DType,
            np.dtypes.Float32DType,
            np.dtypes.Int64DType,
            np.dtypes.Int32DType,
        ]
        # Fixed, hashed author classes have no __new__/__setstate__/reduce hooks.
        # No dynamic global discovery, unsafe fallback or user checkpoint is accepted.
        unsafe = sorted(torch.serialization.get_unsafe_globals_in_checkpoint(checkpoint))
        if unsafe != pins["unsafe_globals"]:
            raise ValueError("YourMT3 checkpoint restoration globals differ from audit")
        with torch.serialization.safe_globals(allowed):
            obj = torch.load(checkpoint, map_location="cpu", weights_only=True)
        state = obj["state_dict"]
        geometry = {}
        for name, tensor in state.items():
            if not isinstance(name, str) or not isinstance(tensor, torch.Tensor):
                raise ValueError("Non-tensor YourMT3 state")
            if not torch.isfinite(tensor).all():
                raise ValueError("Nonfinite YourMT3 state")
            geometry[name] = dict(shape=list(tensor.shape), dtype=str(tensor.dtype))
        if geometry != pins["state"]:
            raise ValueError("Complete YourMT3 state differs from fixed geometry")
        old_codec = obj["hyper_parameters"]["task_manager"].tokenizer.codec
        if {k: asdict(v) for k, v in old_codec._decode_dict.items()} != (
            {k: asdict(v) for k, v in tm.tokenizer.codec._decode_dict.items()}
        ):
            raise ValueError("Checkpoint and current tokenizer token meanings differ")
        from config.config import audio_cfg, model_cfg, shared_cfg  # type: ignore[import-not-found]

        audio, model, shared = deepcopy(audio_cfg), deepcopy(model_cfg), deepcopy(shared_cfg)
        audio.update(codec="spec", hop_length=300)
        model["encoder_type"] = "perceiver-tf"
        shared["TOKENIZER"]["max_shift_steps"] = 206
        from model.ymt3 import YourMT3  # type: ignore[import-not-found]

        net = YourMT3(
            audio_cfg=audio,
            model_cfg=model,
            shared_cfg=shared,
            task_manager=tm,
            write_output_dir=None,
        ).eval()
        configuration = dict(audio=net.audio_cfg, model=net.model_cfg, shared=net.shared_cfg)
        if not configurations_match(configuration, pins["configuration"]):
            raise ValueError("YourMT3 instantiated configuration differs from native audit")
        expected = net.state_dict()
        if set(expected) != set(state) or any(
            expected[k].shape != state[k].shape or expected[k].dtype != state[k].dtype
            for k in state
        ):
            raise ValueError("Complete YourMT3 model key/shape/dtype mismatch")
        net.load_state_dict(state, strict=True)
        del obj, state

        fi = request["pcm"]
        pcm = Path(fi["path"]).resolve(strict=True)

        def verify_pcm() -> None:
            before = pcm.stat()
            if before.st_size != 58 + frames * channels * 8 or (
                before.st_size,
                before.st_mtime_ns,
            ) != (fi["size_bytes"], fi["mtime_ns"]):
                raise ValueError("YourMT3 source PCM geometry/identity changed")
            with pcm.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            after = pcm.stat()
            if actual != fi["sha256"] or (before.st_mtime_ns, before.st_ino) != (
                after.st_mtime_ns,
                after.st_ino,
            ):
                raise ValueError("YourMT3 source PCM hash changed")

        verify_pcm()
        data = np.fromfile(pcm, dtype="<f8", offset=58).reshape(frames, channels)
        if not np.isfinite(data).all() or np.abs(data).max() > 1:
            raise ValueError("Invalid complete source PCM")
        wave = torch.from_numpy(data.astype("float32")).mean(dim=1).unsqueeze(0)
        # Same explicit mono mean + default sinc resampler as the fixed author helper.
        wave = torchaudio.functional.resample(wave, rate, 16000)
        if wave.shape[-1] != count:
            raise ValueError("YourMT3 resampler frame count mismatch")
        with torch.inference_mode():
            for index, start in enumerate(range(0, count, 32767)):
                valid = min(32767, count - start)
                chunk = torch.nn.functional.pad(wave[:, start : start + valid], (0, 32767 - valid))
                tokens = net.inference(chunk.unsqueeze(1)).cpu().numpy()
                if tokens.ndim != 3 or tokens.shape[:2] != (1, 1):
                    raise ValueError("Unexpected native YourMT3 token dimensions")
                windows.append(
                    dict(
                        index=index,
                        start_frame=start,
                        valid_frames=valid,
                        tokens=tokens[0, 0, :].tolist(),
                    )
                )
                write_window_evidence(attempt, windows[-1])
                print(f"window={index}; tokens={tokens.shape[-1]}", flush=True)
        verify_pcm()
    else:
        raw_path = Path(request["raw"]).resolve(strict=True)
        if raw_path.stat().st_size > 16 * 1024**2:
            raise ValueError("YourMT3 raw evidence exceeds budget")
        original = json.loads(raw_path.read_bytes())
        windows = original["windows"]
        configuration = original["configuration"]
    if len(windows) != (count + 32766) // 32767:
        raise ValueError("YourMT3 token replay is missing continuous windows")
    arrays = []
    for index, window in enumerate(windows):
        start = index * 32767
        tokens = window["tokens"]
        if window != dict(
            index=index, start_frame=start, valid_frames=min(32767, count - start), tokens=tokens
        ):
            raise ValueError("YourMT3 token replay window origin/tail mismatch")
        if not 1 <= len(tokens) <= 1024 or any(
            type(t) is not int or not 0 <= t < 596 for t in tokens
        ):
            raise ValueError("Invalid YourMT3 token replay")
        arrays.append(np.array([tokens], dtype=np.int64))
    starts = [w["start_frame"] / 16000 for w in windows]
    zipped, events, errors = tm.detokenize_list_batches(arrays, starts, return_events=True)

    def jsonable(value: Any) -> Any:
        if is_dataclass(value) and not isinstance(value, type):
            return jsonable(asdict(value))
        if isinstance(value, dict):
            return {str(k): jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [jsonable(v) for v in (sorted(value) if isinstance(value, set) else value)]
        return value

    decoded = jsonable(deepcopy(zipped))  # Merge may mutate note events; retain pre-merge evidence.
    from utils.event2note import merge_zipped_note_events_and_ties_to_notes  # type: ignore[import-not-found]

    notes, merge_errors = merge_zipped_note_events_and_ties_to_notes(zipped)
    result = dict(
        notes=[asdict(n) for n in notes],
        decoded_windows=decoded,
        events=jsonable(events),
        decode_errors={k: int(v) for k, v in Counter(errors).items()},
        merge_errors={k: int(v) for k, v in Counter(merge_errors).items()},
    )
    if mode == "infer":
        spec = importlib.util.spec_from_file_location(
            "yourmt3_memory", Path(__file__).with_name("process_metrics.py")
        )
        assert spec is not None and spec.loader is not None
        memory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(memory)
        working, commit = memory.peak_process_memory()
        result.update(
            windows=windows,
            configuration=configuration,
            versions=versions,
            seconds=time.monotonic() - started,
            peak_working_set_bytes=working,
            peak_commit_bytes=commit,
        )
    with (attempt / "native.json").open("x", encoding="utf-8") as output_stream:
        json.dump(result, output_stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
