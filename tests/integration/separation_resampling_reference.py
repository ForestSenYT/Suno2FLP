"""Opt-in independent scalar FIR reference; never imports native packages by default."""

import importlib
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def i0(value: float) -> float:
    term = total = 1.0
    for index in range(1, 100):
        term *= value * value / (4 * index * index)
        total += term
        if term < total * 1e-17:
            return total
    raise ValueError("Scalar Kaiser reference did not converge")


def reference(values: list[float], up: int, down: int, *, single: bool) -> list[float]:
    if up == down == 1:
        return list(values)
    half = 10 * max(up, down)
    cutoff = 1 / max(up, down)
    taps = []
    for position in range(-half, half + 1):
        x = cutoff * position
        sinc = 1.0 if position == 0 else math.sin(math.pi * x) / (math.pi * x)
        taps.append(cutoff * sinc * i0(5 * math.sqrt(max(0.0, 1 - (position / half) ** 2))) / i0(5))
    total = math.fsum(taps)
    taps = [f32(f32(v / total) * up) if single else v / total * up for v in taps]
    pre_pad = down - half % down
    remove = (half + pre_pad) // down
    count = (len(values) * up + down - 1) // down
    result = []
    for index in range(count):
        terms = []
        for n, value in enumerate(values):
            tap = (index + remove) * down - n * up - pre_pad
            if 0 <= tap < len(taps):
                terms.append(value * taps[tap])
        if single:
            accumulator = 0.0
            for term in terms:
                accumulator = f32(accumulator + f32(term))
            result.append(accumulator)
        else:
            result.append(math.fsum(terms))
    return result


def main() -> None:
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    root, packages, owned = request_path.parent, Path(request["packages"]), Path(request["owned"])
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("Reference child requires isolated startup")

    def load(name: str):
        spec = importlib.util.spec_from_file_location(f"_reference_{name}", owned / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    helper, worker = load("spleeter_worker"), load("spleeter_separation_worker")
    helper.isolate_environment(packages, root)
    sys.path.insert(0, str(packages))
    np, signal = importlib.import_module("numpy"), importlib.import_module("scipy.signal")
    assert np.__version__ == "1.24.3" and importlib.import_module("scipy").__version__ == "1.15.3"
    evidence = []
    # Frozen before execution: compares scalar arithmetic to pinned native FIR.
    tolerance = 2e-6
    for rate in (8000, 16000, 22050, 44100, 48000, 96000, 192000):
        for channels in (1, 2):
            case = root / f"{rate}-{channels}"
            case.mkdir()
            frames = 37
            pairs = [
                (
                    0.75 if n == 0 else -0.5 if n == 36 else 0.1 * math.sin(n),
                    -0.625 if n == 0 else 0.375 if n == 36 else 0.15 * math.cos(n),
                )
                for n in range(frames)
            ]
            source = [p[:channels] for p in pairs]
            size = frames * channels * 8
            header = struct.pack(
                "<4sI4s4sIHHIIHHH4sII4sI",
                b"RIFF",
                size + 50,
                b"WAVE",
                b"fmt ",
                18,
                3,
                channels,
                rate,
                rate * channels * 8,
                channels * 8,
                64,
                0,
                b"fact",
                4,
                frames,
                b"data",
                size,
            )
            pcm = case / "source.wav"
            with pcm.open("xb") as stream:
                stream.write(
                    header + b"".join(struct.pack("<" + "d" * channels, *p) for p in source)
                )
            model_frames = worker.prepare_input(np, signal, pcm, case, frames, rate, channels)
            model_raw = (case / "model-input.f32").read_bytes()
            model = list(struct.iter_unpack("<ff", model_raw))
            common = math.gcd(rate, 44100)
            expected = [
                reference(
                    [p[c if channels == 2 else 0] for p in source],
                    44100 // common,
                    rate // common,
                    single=False,
                )
                for c in (0, 1)
            ]
            assert model_frames == len(model) == (frames * 44100 + rate - 1) // rate
            forward_error = max(
                abs(value - f32(expected[c][n]))
                for n, p in enumerate(model)
                for c, value in enumerate(p)
            )
            assert forward_error <= tolerance, (rate, channels, forward_error)
            for stem in worker.STEMS:
                with (case / f"model.{stem}.f32").open("xb") as stream:
                    stream.write(model_raw)
            result = worker.source_outputs(np, signal, case, frames, rate, model_frames)
            returned = (case / "vocals.wav").read_bytes()
            tail = (case / "vocals.tail.f32").read_bytes()
            back = list(struct.iter_unpack("<ff", returned[58:] + tail))
            expected_back = [
                reference([p[c] for p in model], rate // common, 44100 // common, single=True)
                for c in (0, 1)
            ]
            expected_length = (model_frames * rate + 44099) // 44100
            assert len(back) == result["returned_source_frames"] == expected_length
            assert len(returned) == 58 + frames * 8 and len(tail) == (expected_length - frames) * 8
            backward_error = max(
                abs(value - expected_back[c][n])
                for n, p in enumerate(back)
                for c, value in enumerate(p)
            )
            assert backward_error <= tolerance, (rate, channels, backward_error)
            evidence.append(
                dict(
                    rate=rate,
                    channels=channels,
                    frames=frames,
                    model_frames=model_frames,
                    returned_frames=expected_length,
                    tail_frames=expected_length - frames,
                    forward_max_error=forward_error,
                    backward_max_error=backward_error,
                )
            )
    with (root / "reference.json").open("x", encoding="utf-8") as stream:
        json.dump(
            dict(
                profile="independent-scalar-resampling-v1",
                tolerance=tolerance,
                cases=evidence,
                model_inference="not_executed",
            ),
            stream,
            indent=2,
        )


if __name__ == "__main__":
    main()
