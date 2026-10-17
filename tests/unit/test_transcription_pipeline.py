"""Real decoder plus explicitly simulated native protocol; these are not model quality tests."""

import json
import struct
import wave
from pathlib import Path

import pytest

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.transcription import BasicPitchBackend
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.pipeline.transcription import transcribe_audio
from suno2flp.validator.transcription import verify_transcription


@pytest.fixture
def protocol(tmp_path: Path, monkeypatch):
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 22050)
    decode = tmp_path / "decode"
    decode_pcm_wave(source, decode)
    backend = tmp_path / "backend"
    (backend / "packages/pkg").mkdir(parents=True)
    module = backend / "packages/pkg/__init__.py"
    module.write_bytes(b"# explicitly simulated protocol")
    module_id = capture_stream_input(module)
    (backend / "backend.json").write_text("{}", encoding="utf-8")
    record = BasicPitchBackend(
        root=backend,
        python=module_id,
        runtime=[],
        artifacts=[],
        adapters=[],
        payload={"pkg/__init__.py": module_id.sha256},
    )

    def read(root):
        assert root == backend
        return record.model_copy(deep=True)

    def call(record, attempt, request, **kwargs):
        if kwargs.get("should_cancel") and kwargs["should_cancel"]():
            raise ValueError("cancelled")
        (attempt / "request.json").write_text(
            json.dumps({**request, "packages": str(record.root / "packages")}), encoding="utf-8"
        )
        for name, width in (("note", 88), ("onset", 88), ("contour", 264)):
            (attempt / f"{name}.f32").write_bytes(b"\0" * (172 * width * 4))
        (attempt / "mono.f32").write_bytes(b"\0" * (22050 * 4))
        (attempt / "bends.i8").write_bytes(bytes([0, 1, 255, 0] * 5))
        (attempt / "stdout.bin").write_bytes(b"")
        (attempt / "stderr.bin").write_bytes(b"")
        probe = {
            "profile": "basic-pitch-native-probe-v1",
            "provider": "CPUExecutionProvider",
            "intra_op_threads": 8,
            "inter_op_threads": 1,
            "sequential": True,
            "repeatable": True,
            "shapes": {"note": [1, 172, 88], "onset": [1, 172, 88], "contour": [1, 172, 264]},
            "versions": {
                "onnxruntime": "1.23.2",
                "numpy": "2.3.5",
                "scipy": "1.16.3",
                "basic-pitch": "0.4.0",
            },
            "modules": {
                name: str(module)
                for name in (
                    "numpy",
                    "onnxruntime",
                    "scipy",
                    "basic_pitch",
                    "librosa",
                    "pretty_midi",
                    "mir_eval",
                    "resampy",
                )
            },
        }
        notes = [
            {"start_frame": 10, "end_frame": 20, "pitch": 60, "activation": 0.7, "bend_offset": 0},
            {"start_frame": 15, "end_frame": 25, "pitch": 64, "activation": 0.6, "bend_offset": 10},
        ]
        result = {
            "probe": probe,
            "resampled_frames": 22050,
            "windows": 1,
            "owned_rows": 87,
            "notes": notes,
            "bend_bytes": 20,
        }
        (attempt / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return b"", b""

    monkeypatch.setattr("suno2flp.pipeline.transcription.read_basic_pitch", read)
    monkeypatch.setattr("suno2flp.pipeline.transcription.call_basic_pitch", call)
    monkeypatch.setattr("suno2flp.validator.transcription.read_basic_pitch", read)
    return source, decode / "decode.json", backend


def test_source_bound_candidate_replays_and_keeps_overlapping_bends(protocol, tmp_path):
    source, decode, backend = protocol
    before = capture_stream_input(source)
    result = transcribe_audio(decode, backend, tmp_path / "candidate")
    assert len(result.result.notes) == 2
    assert result.bends.size_bytes == 20
    assert result.writer_eligibility == "blocked" and result.execution_allowed is False
    assert (
        verify_transcription(tmp_path / "candidate/transcription.json", tmp_path / "replay")
        == result
    )
    assert capture_stream_input(source) == before
    with pytest.raises((ValueError, FileExistsError)):
        transcribe_audio(decode, backend, tmp_path / "candidate")


def test_rehashed_forged_predictions_fail_fresh_inference(protocol, tmp_path):
    _, decode, backend = protocol
    result = transcribe_audio(decode, backend, tmp_path / "candidate")
    path = result.predictions[0].file.path
    data = path.read_bytes()
    path.write_bytes(struct.pack("<f", 0.5) + data[4:])
    result.predictions[0].file = capture_stream_input(path)
    report = tmp_path / "candidate/transcription.json"
    report.write_text(result.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="replay"):
        verify_transcription(report, tmp_path / "replay")


def test_cancel_cannot_publish(protocol, tmp_path):
    _, decode, backend = protocol
    with pytest.raises(Exception, match="cancel"):
        transcribe_audio(decode, backend, tmp_path / "cancelled", should_cancel=lambda: True)
    assert not (tmp_path / "cancelled/transcription.json").exists()


@pytest.mark.parametrize("corruption", ["nonfinite", "negative", "over-one", "truncated", "bend"])
def test_incomplete_or_invalid_numeric_evidence_cannot_publish(
    protocol, tmp_path, monkeypatch, corruption
):
    _, decode, backend = protocol
    import suno2flp.pipeline.transcription as pipeline

    original = pipeline.call_basic_pitch

    def corrupt(record, attempt, request, **kwargs):
        result = original(record, attempt, request, **kwargs)
        path = attempt / "note.f32"
        raw = path.read_bytes()
        if corruption == "truncated":
            path.write_bytes(raw[:-4])
        elif corruption == "bend":
            (attempt / "bends.i8").write_bytes(bytes([26]) * 20)
        else:
            value = {"nonfinite": float("nan"), "negative": -0.1, "over-one": 1.1}[corruption]
            path.write_bytes(struct.pack("<f", value) + raw[4:])
        return result

    monkeypatch.setattr(pipeline, "call_basic_pitch", corrupt)
    with pytest.raises(ValueError):
        transcribe_audio(decode, backend, tmp_path / "invalid")
    assert not (tmp_path / "invalid/transcription.json").exists()
