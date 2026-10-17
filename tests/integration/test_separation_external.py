"""Opt-in complete native separation, replay and scalar resampling evidence."""

import json
import math
import os
import platform
import struct
import sys
import wave
from pathlib import Path

import pytest

from suno2flp.core.offline_files import capture_stream_input, verify_inputs
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.integrations.codec_process import run_bounded_process
from suno2flp.integrations.spleeter_backend import call_spleeter_separation, provision_spleeter
from suno2flp.pipeline.separation import separate_audio
from suno2flp.validator.separation import verify_separation

pytestmark = pytest.mark.external


def _prerequisite() -> Path:
    artifacts = os.environ.get("SUNO2FLP_SPLEETER_ARTIFACTS")
    if not artifacts:
        pytest.skip("Set SUNO2FLP_SPLEETER_ARTIFACTS to the fixed local 55 artifacts")
    if sys.platform != "win32" or platform.python_version() != "3.11.16":
        pytest.skip("Native separation profile requires Windows CPython3.11.16 x64")
    return Path(artifacts)


def test_native_complete_source_and_replay(tmp_path: Path) -> None:
    artifacts = _prerequisite()
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 48000, 0, "NONE", "original resampling fixture"))
        stream.writeframes(b"\0\0" * 37 + b"\0\x40" + b"\0\0" * 1001)
    before = capture_stream_input(source)
    decode_pcm_wave(source, tmp_path / "decode")
    backend = provision_spleeter(tmp_path / "backend", artifacts)
    first = separate_audio(tmp_path / "decode/decode.json", backend.root, tmp_path / "candidate")
    assert first.frames == 1039 and first.channels == 1
    assert first.result.returned_source_frames >= first.frames
    assert verify_separation(tmp_path / "candidate/separation.json", tmp_path / "replay") == first
    assert (tmp_path / "replay/replay.json").is_file()
    verify_inputs([before])


def test_native_scalar_resampling_reference(tmp_path: Path) -> None:
    artifacts = _prerequisite()
    backend = provision_spleeter(tmp_path / "backend", artifacts)
    root = tmp_path / "reference"
    root.mkdir()
    script = Path(__file__).with_name("separation_resampling_reference.py")
    request = root / "request.json"
    with request.open("x", encoding="utf-8") as stream:
        json.dump(
            dict(
                packages=str(backend.root / "packages"),
                owned=str(Path(__file__).parents[2] / "src/suno2flp/integrations"),
            ),
            stream,
        )
    identities = [capture_stream_input(script), capture_stream_input(request)]
    stdout, stderr = run_bounded_process(
        [str(backend.python.path), "-I", "-S", "-B", str(script), str(request)], timeout=300
    )
    (root / "stdout.bin").write_bytes(stdout)
    (root / "stderr.bin").write_bytes(stderr)
    report = json.loads((root / "reference.json").read_text())
    assert len(report["cases"]) == 14 and report["model_inference"] == "not_executed"
    verify_inputs(identities)


def test_bounded_graph_matches_full_graph_across_two_boundaries(tmp_path: Path) -> None:
    artifacts = _prerequisite()
    frames, rate = 1044481, 44100
    peaks = (0, 520155, 520211, 1044480)
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((2, 2, rate, 0, "NONE", "original boundary signal"))
        for start in range(0, frames, 4096):
            raw = bytearray()
            for index in range(start, min(frames, start + 4096)):
                pulse = 0.75 if index in peaks else 0
                raw.extend(
                    struct.pack(
                        "<hh",
                        int(32767 * (pulse + 0.12 * math.sin(2 * math.pi * 220 * index / rate))),
                        int(32767 * (pulse + 0.09 * math.sin(2 * math.pi * 337 * index / rate))),
                    )
                )
            stream.writeframesraw(raw)
    before = capture_stream_input(source)
    decoded = decode_pcm_wave(source, tmp_path / "decode")
    backend = provision_spleeter(tmp_path / "backend", artifacts)
    bounded, full = tmp_path / "bounded", tmp_path / "full"
    bounded.mkdir()
    full.mkdir()
    _, result = call_spleeter_separation(
        backend,
        bounded,
        dict(
            operation="separate",
            pcm=str(decoded.pcm.path),
            frames=frames,
            sample_rate=rate,
            channels=2,
        ),
    )
    assert len(result.partitions) == 3 and result.partitions[-1].partition.stft_frames == 1
    script = Path(__file__).with_name("separation_graph_reference.py")
    request = full / "request.json"
    request.write_text(
        json.dumps(
            dict(
                packages=str(backend.root / "packages"),
                owned=str(Path(__file__).parents[2] / "src/suno2flp/integrations"),
                model_input=str(bounded / "model-input.f32"),
                frames=frames,
            )
        ),
        encoding="utf-8",
    )
    identities = [before, capture_stream_input(script), capture_stream_input(request)]
    stdout, stderr = run_bounded_process(
        [str(backend.python.path), "-I", "-S", "-B", str(script), str(request)], timeout=1800
    )
    (full / "stdout.bin").write_bytes(stdout)
    (full / "stderr.bin").write_bytes(stderr)
    proof = json.loads((full / "result.json").read_text())
    assert proof["execution"] == result.execution.model_dump(mode="json")
    for stem in ("vocals", "drums", "bass", "other"):
        assert capture_stream_input(full / f"{stem}.f32").sha256 == proof["output_sha256"][stem]
        with (
            (bounded / f"model.{stem}.f32").open("rb") as actual,
            (full / f"{stem}.f32").open("rb") as expected,
        ):
            while raw := actual.read(65536):
                reference = expected.read(len(raw))
                assert len(reference) == len(raw)
                assert (
                    max(
                        abs(a[0] - b[0])
                        for a, b in zip(
                            struct.iter_unpack("<f", raw),
                            struct.iter_unpack("<f", reference),
                            strict=True,
                        )
                    )
                    <= 1e-5
                )
            assert not expected.read(1)
    for peak in peaks:
        low, high = max(0, peak - 8), min(frames, peak + 9)
        values = []
        for stem in ("vocals", "drums", "bass", "other"):
            with (bounded / f"model.{stem}.f32").open("rb") as stream:
                stream.seek(low * 8)
                values.append(
                    [p[0] for p in struct.iter_unpack("<ff", stream.read((high - low) * 8))]
                )
        summed = [math.fsum(row) for row in zip(*values, strict=True)]
        assert abs(low + max(range(len(summed)), key=lambda j: abs(summed[j])) - peak) <= 1
    verify_inputs(identities)
