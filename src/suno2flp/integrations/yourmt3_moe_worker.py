"""Fixed CPU MoE inference and independent decoding, with retained capped prefixes."""

import hashlib
import importlib.metadata
import importlib.util
import json
import math
import socket
import sys
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Any


def integer_error_counts(values: dict[str, Any]) -> dict[str, int]:
    result = {}
    for name, value in values.items():
        if (
            not isinstance(name, str)
            or isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("Expected exact nonnegative error occurrences")
        number = int(value) if isinstance(value, Integral) else int(float(value))
        if value != number:
            raise ValueError("Expected exact nonnegative error occurrences")
        result[name] = number
    return result


def moe_configuration(
    audio: dict[str, Any], model: dict[str, Any], shared: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    audio, model, shared = deepcopy(audio), deepcopy(model), deepcopy(shared)
    audio.update(codec="spec", hop_length=300)
    model.update(encoder_type="perceiver-tf", decoder_type="multi-t5")
    model["encoder"]["perceiver-tf"].update(
        num_latents=26,
        sca_use_query_residual=True,
        ff_layer_type="moe",
        ff_widening_factor=4,
        moe_num_experts=8,
        moe_topk=2,
        hidden_act="silu",
        position_encoding_type="rope",
        rope_partial_pe=True,
    )
    shared["TOKENIZER"]["max_shift_steps"] = 206
    return audio, model, shared


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in (sorted(value) if isinstance(value, set) else value)]
    return value


def _selected(window: dict[str, Any]) -> list[list[int]]:
    if set(window) != {"index", "start_frame", "valid_frames", "initial", "retry"}:
        raise ValueError("Unexpected MoE window trace")
    for streams, maximum in [(window["initial"], 256), (window["retry"], 1024)]:
        if streams is None:
            continue
        if not isinstance(streams, list) or len(streams) != 13:
            raise ValueError("Expected all13 MoE channels")
        for index, stream in enumerate(streams):
            if (
                set(stream) != {"channel", "tokens"}
                or type(stream["channel"]) is not int
                or stream["channel"] != index
                or not isinstance(stream["tokens"], list)
                or not 1 <= len(stream["tokens"]) <= maximum
                or any(type(token) is not int or not 0 <= token < 596 for token in stream["tokens"])
            ):
                raise ValueError("Invalid addressed MoE token stream")
        lengths = {len(stream["tokens"]) for stream in streams}
        if len(lengths) != 1 or (
            any(1 not in stream["tokens"] for stream in streams) and lengths != {maximum}
        ):
            raise ValueError("Incomplete MoE token stream geometry")
    if not isinstance(window["initial"], list):
        raise ValueError("Missing initial MoE trace")
    needed = any(1 not in stream["tokens"] for stream in window["initial"])
    if needed != (window["retry"] is not None):
        raise ValueError("MoE retry differs from the fixed capped-EOS policy")
    if window["retry"] is not None and any(
        after["tokens"][:256] != before["tokens"]
        for before, after in zip(window["initial"], window["retry"], strict=True)
    ):
        raise ValueError("MoE retry changed initial generation tokens")
    return [
        stream["tokens"]
        for stream in (window["retry"] if window["retry"] is not None else window["initial"])
    ]


def infer_window(
    generate: Callable[[int], Any],
    attempt: Path,
    *,
    index: int,
    start: int,
    valid: int,
) -> dict[str, Any]:
    """Journal every returned array before retry execution or trace validation."""
    if type(index) is not int or not 0 <= index <= 292:
        raise ValueError("Invalid MoE generation journal address")
    coordinates = dict(index=index, start_frame=start, valid_frames=valid)

    def streams(maximum: int, phase: str) -> list[dict[str, Any]]:
        raw = deepcopy(generate(maximum))
        with (attempt / f"generation-{index:03}-{phase}.json").open(
            "x", encoding="utf-8"
        ) as output:
            json.dump(
                dict(**coordinates, max_token_length=maximum, tokens=raw),
                output,
                indent=2,
                allow_nan=False,
            )
        if (
            not isinstance(raw, list)
            or len(raw) != 1
            or not isinstance(raw[0], list)
            or len(raw[0]) != 13
            or any(not isinstance(tokens, list) for tokens in raw[0])
        ):
            raise ValueError("Unexpected MoE native dimensions")
        return [dict(channel=channel, tokens=tokens) for channel, tokens in enumerate(raw[0])]

    window: dict[str, Any] = dict(**coordinates, initial=streams(256, "initial"), retry=None)
    if any(1 not in stream["tokens"] for stream in window["initial"]):
        window["retry"] = streams(1024, "retry")
    _selected(window)
    with (attempt / f"window-{index:03}.json").open("x", encoding="utf-8") as output:
        json.dump(window, output, indent=2, allow_nan=False)
    return window


def main() -> None:
    started = time.monotonic()
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise ValueError("MoE worker requires -I -S -B")
    path = Path(sys.argv[1]).resolve(strict=True)
    if path.stat().st_size > 65536:
        raise ValueError("MoE request exceeds budget")
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
        raise ValueError("Unexpected MoE request fields")
    mode = request["mode"]
    frames, rate, channels = (request[k] for k in ("frames", "sample_rate", "channels"))
    if (
        mode not in ("infer", "decode")
        or type(frames) is not int
        or type(rate) is not int
        or type(channels) is not int
        or not 8000 <= rate <= 192000
        or not 0 < frames <= rate * 600
        or channels not in (1, 2)
    ):
        raise ValueError("Unsupported complete MoE source geometry")
    attempt = path.parent
    (attempt / "tmp").mkdir()
    common = _module("yourmt3_common", Path(__file__).with_name("yourmt3_worker.py"))
    common.configure_environment(attempt)

    def no_network(*args: object, **kwargs: object) -> Any:
        raise RuntimeError("MoE network/download fallback disabled")

    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.socket.connect_ex = no_network  # type: ignore[method-assign]
    socket.socket.sendto = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network
    packages = Path(request["packages"]).resolve(strict=True)
    pins = json.loads(Path(request["pins"]).read_bytes())
    if pins["profile"] != "yourmt3-moe-cpu-windows-cp311-v1" or pins["generation_policy"] != {
        "initial_max_tokens": 256,
        "retry_max_tokens": 1024,
        "max_retries": 1,
    }:
        raise ValueError("Unsupported fixed MoE profile/generation policy")
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
        raise ValueError("Fixed MoE profile requires CPU-only Torch")
    versions = {
        p["distribution"]: importlib.metadata.version(p["distribution"]) for p in pins["wheels"]
    }
    if versions != {p["distribution"]: p["version"] for p in pins["wheels"]}:
        raise ValueError("MoE installed versions differ from fixed wheels")
    from utils.task_manager import TaskManager  # type: ignore[import-not-found]

    tm = TaskManager(task_name="mc13_full_plus_256", max_shift_steps=206)
    if not common.configurations_match(_plain(tm.program2channel_vocab), pins["program_channels"]):
        raise ValueError("MoE source program/channel vocabulary differs from audit")
    count = (frames * 16000 + rate - 1) // rate
    windows: list[dict[str, Any]] = []
    if mode == "infer":
        checkpoint = packages / "models/last.ckpt"
        with checkpoint.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if checkpoint.stat().st_size != 561544628 or digest != (
            "ae38e415c79efd5592dcb9b658cdb99ddb11d4c4e1eaa364cab04a052473fc25"
        ):
            raise ValueError("Fixed MoE checkpoint identity changed")
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
        if (
            sorted(torch.serialization.get_unsafe_globals_in_checkpoint(checkpoint))
            != pins["unsafe_globals"]
        ):
            raise ValueError("MoE restoration globals differ from fixed audit")
        with torch.serialization.safe_globals(allowed):
            obj = torch.load(checkpoint, map_location="cpu", weights_only=True)
        state = obj["state_dict"]
        geometry = {}
        for name, tensor in state.items():
            if (
                not isinstance(name, str)
                or not isinstance(tensor, torch.Tensor)
                or not torch.isfinite(tensor).all()
            ):
                raise ValueError("Invalid complete MoE state")
            geometry[name] = dict(shape=list(tensor.shape), dtype=str(tensor.dtype))
        if geometry != pins["state"]:
            raise ValueError("Complete MoE state differs from fixed geometry")
        old_codec = obj["hyper_parameters"]["task_manager"].tokenizer.codec
        if {k: asdict(v) for k, v in old_codec._decode_dict.items()} != {
            k: asdict(v) for k, v in tm.tokenizer.codec._decode_dict.items()
        }:
            raise ValueError("MoE checkpoint token meanings differ from current source")
        from config.config import audio_cfg, model_cfg, shared_cfg  # type: ignore[import-not-found]
        from model.ymt3 import YourMT3  # type: ignore[import-not-found]

        audio, model, shared = moe_configuration(audio_cfg, model_cfg, shared_cfg)
        net = YourMT3(
            audio_cfg=audio,
            model_cfg=model,
            shared_cfg=shared,
            task_manager=tm,
            write_output_dir=None,
        ).eval()
        configuration = dict(audio=net.audio_cfg, model=net.model_cfg, shared=net.shared_cfg)
        if not common.configurations_match(configuration, pins["configuration"]):
            raise ValueError("MoE instantiated configuration differs from audit")
        expected = net.state_dict()
        if set(expected) != set(state) or any(
            expected[k].shape != state[k].shape or expected[k].dtype != state[k].dtype
            for k in state
        ):
            raise ValueError("MoE strict state key/shape/dtype mismatch")
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
                raise ValueError("MoE PCM geometry/identity changed")
            with pcm.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            after = pcm.stat()
            if actual != fi["sha256"] or (before.st_mtime_ns, before.st_ino) != (
                after.st_mtime_ns,
                after.st_ino,
            ):
                raise ValueError("MoE complete PCM bytes changed")

        verify_pcm()
        data = np.fromfile(pcm, dtype="<f8", offset=58).reshape(frames, channels)
        if not np.isfinite(data).all() or np.abs(data).max() > 1:
            raise ValueError("Invalid complete MoE input PCM")
        wave = torch.from_numpy(data.astype("float32")).mean(dim=1).unsqueeze(0)
        wave = torchaudio.functional.resample(wave, rate, 16000)
        if wave.shape[-1] != count:
            raise ValueError("MoE resampled frame count differs from original clock")
        with torch.inference_mode():
            for index, start in enumerate(range(0, count, 32767)):
                valid = min(32767, count - start)
                chunk = torch.nn.functional.pad(
                    wave[:, start : start + valid], (0, 32767 - valid)
                ).unsqueeze(1)

                def generate(maximum: int, chunk: Any = chunk) -> Any:
                    return net.inference(chunk, max_token_length=maximum).cpu().numpy().tolist()

                window = infer_window(
                    generate,
                    attempt,
                    index=index,
                    start=start,
                    valid=valid,
                )
                windows.append(window)
                print(f"window={index}; retry={window['retry'] is not None}", flush=True)
        verify_pcm()
    else:
        raw_path = Path(request["raw"]).resolve(strict=True)
        if raw_path.stat().st_size > 64 * 1024**2:
            raise ValueError("MoE replay evidence exceeds budget")
        windows = json.loads(raw_path.read_bytes())["windows"]
    if len(windows) != (count + 32766) // 32767:
        raise ValueError("MoE replay misses continuous windows")
    arrays = []
    starts = []
    for index, window in enumerate(windows):
        start = index * 32767
        if any(type(window[k]) is not int for k in ("index", "start_frame", "valid_frames")) or (
            window["index"],
            window["start_frame"],
            window["valid_frames"],
        ) != (index, start, min(32767, count - start)):
            raise ValueError("MoE global window origin or tail changed")
        arrays.append(np.array([_selected(window)], dtype=np.int64))
        starts.append(start / 16000)
    from utils.event2note import merge_zipped_note_events_and_ties_to_notes  # type: ignore[import-not-found]

    decoded = []
    for channel in range(13):
        zipped, events, errors = tm.detokenize_list_batches(
            [tokens[:, channel, :] for tokens in arrays], starts, return_events=True
        )
        before = _plain(deepcopy(zipped))
        notes, merge_errors = merge_zipped_note_events_and_ties_to_notes(zipped)
        decoded.append(
            dict(
                channel=channel,
                notes=[asdict(note) for note in notes],
                decoded_windows=before,
                events=_plain(events),
                decode_errors=integer_error_counts(errors),
                merge_errors=integer_error_counts(merge_errors),
            )
        )
    result: dict[str, Any] = dict(channels=decoded)
    if mode == "infer":
        memory = _module("yourmt3_memory", Path(__file__).with_name("process_metrics.py"))
        working, commit = memory.peak_process_memory()
        if max(working, commit) > 16 * 1024**3:
            raise ValueError("MoE observed native memory peak exceeds budget")
        result.update(
            windows=windows,
            configuration=configuration,
            versions=versions,
            seconds=time.monotonic() - started,
            peak_working_set_bytes=working,
            peak_commit_bytes=commit,
        )
    content = json.dumps(result, indent=2, allow_nan=False).encode("utf-8")
    if len(content) > 64 * 1024**2:
        raise ValueError("MoE native output exceeds complete evidence budget")
    with (attempt / "native.json").open("xb") as output:
        output.write(content)


if __name__ == "__main__":
    main()
