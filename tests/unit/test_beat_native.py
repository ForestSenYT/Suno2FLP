"""Tiny complete native witnesses, validated without any native model packages."""

import hashlib
import struct
from pathlib import Path

import pytest

from suno2flp.core.beat_native import NativeBeatResult
from suno2flp.integrations.beat_backend import load_beat_pins
from suno2flp.validator.beat_native import validate_native_beats


@pytest.fixture
def native(tmp_path: Path):
    pins = load_beat_pins()
    pcm = tmp_path / "source.wav"
    pcm.write_bytes(bytes(58 + 1025 * 8))
    attempt = tmp_path / "native"
    attempt.mkdir()
    arrays = {
        "mono.f64": ([1025], "<f8", bytes(1025 * 8)),
        "resampled.f64": ([1025], "<f8", bytes(1025 * 8)),
        "wave.f32": ([1025], "<f4", bytes(1025 * 4)),
        "spect.f32": ([3, 128], "<f4", bytes(3 * 128 * 4)),
        "chunk-0-input.f32": ([15, 128], "<f4", bytes(15 * 128 * 4)),
        "chunk-0-beat.f32": ([15], "<f4", struct.pack("<15f", *([-1] * 7 + [1] + [-1] * 7))),
        "chunk-0-downbeat.f32": ([15], "<f4", struct.pack("<15f", *([-1] * 7 + [1] + [-1] * 7))),
        "beat.f32": ([3], "<f4", struct.pack("<3f", -1, 1, -1)),
        "downbeat.f32": ([3], "<f4", struct.pack("<3f", -1, 1, -1)),
        "beats.f64": ([1], "<f8", struct.pack("<d", 0.02)),
        "downbeats.f64": ([1], "<f8", struct.pack("<d", 0.02)),
    }
    files = {}
    for name, (shape, encoding, raw) in arrays.items():
        (attempt / name).write_bytes(raw)
        files[name] = dict(
            shape=shape,
            encoding=encoding,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    result = NativeBeatResult.model_validate(
        dict(
            execution=dict(
                profile="beat-this-final0-fixed-cpu-v1",
                intra_op_threads=8,
                inter_op_threads=1,
                deterministic_algorithms=True,
                mkldnn=False,
                cuda=None,
                matmul_precision="highest",
                model_state_sha256=pins.model_state_sha256,
                geometry={k: v.model_dump() for k, v in pins.model_geometry.items()},
                versions={},
                modules={},
            ),
            frames=1025,
            sample_rate=22050,
            channels=1,
            chunk_starts=[-6],
            files=files,
            source_peak=0.0,
            mono_peak=0.0,
            inference_seconds=0.1,
            worker_seconds=0.2,
            peak_working_set=1024,
            peak_commit=2048,
        )
    )
    return pcm, attempt, result


def test_complete_witness_replays_exact_source_and_peaks(native) -> None:
    pcm, attempt, result = native
    peaks, identities = validate_native_beats(attempt, result, pcm)
    assert peaks.beat_peaks == [1]
    assert len(identities) == 11


@pytest.mark.parametrize(
    "mutation", ["mono", "chunk", "aggregation", "seconds", "foreign-file", "path"]
)
def test_coherent_witness_rehashing_cannot_hide_processing_changes(native, mutation) -> None:
    pcm, attempt, result = native
    if mutation == "foreign-file":
        (attempt / "unreported.f32").write_bytes(b"unreported")
    elif mutation == "path":
        result.files["../escape.f32"] = result.files.pop("beat.f32")
    else:
        name = {
            "mono": "mono.f64",
            "chunk": "chunk-0-input.f32",
            "aggregation": "beat.f32",
            "seconds": "beats.f64",
        }[mutation]
        target = attempt / name
        raw = bytearray(target.read_bytes())
        raw[-1] ^= 1
        target.write_bytes(raw)
        result.files[name].sha256 = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        validate_native_beats(attempt, result, pcm)
