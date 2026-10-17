"""Actual decoding and explicitly simulated native protocol; no music claims."""

import hashlib
import shutil
import struct
import wave
from pathlib import Path

import pytest
from test_beat_native import native as native

from suno2flp.core.beat_runtime import BeatBackend
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.integrations.beat_backend import beat_request
from suno2flp.pipeline.beat_analysis import analyze_beats
from suno2flp.validator.beat_analysis import verify_beat_analysis


@pytest.fixture
def protocol(native, tmp_path, monkeypatch):
    _, native_root, native_result = native
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        stream.writeframes(bytes(1025 * 2))
    decode_pcm_wave(source, tmp_path / "decode")
    root = tmp_path / "backend"
    root.mkdir()
    (root / "backend.json").write_bytes(b"{}")
    witness = capture_stream_input(root / "backend.json")
    record = BeatBackend(
        root=root, python=witness, runtime=[witness], artifacts=[], adapters=[], payload={}
    )
    calls = []

    def read(path, **kwargs):
        assert path == root
        return record.model_copy(deep=True)

    def call(backend, attempt, pcm, frames, rate, channels, **kwargs):
        calls.append(attempt)
        assert (frames, rate, channels) == (1025, 22050, 1)
        for path in native_root.iterdir():
            shutil.copyfile(path, attempt / path.name)
        import json

        (attempt / "request.json").write_text(
            json.dumps(beat_request(backend, pcm, frames, rate, channels)), encoding="utf-8"
        )
        (attempt / "result.json").write_text(native_result.model_dump_json(), encoding="utf-8")
        return native_result.model_copy(deep=True)

    monkeypatch.setattr("suno2flp.pipeline.beat_analysis.read_beat_backend", read)
    monkeypatch.setattr("suno2flp.pipeline.beat_analysis.call_beat_backend", call)
    monkeypatch.setattr("suno2flp.validator.beat_analysis.read_beat_backend", read)
    return source, tmp_path / "decode/decode.json", root, calls


def test_candidate_keeps_exact_source_and_owns_fresh_replay(protocol, tmp_path: Path) -> None:
    source, decode, backend, calls = protocol
    before = capture_stream_input(source)
    result = analyze_beats(decode, backend, tmp_path / "candidate")
    assert result.beats[0].microseconds.numerator == 20000
    assert result.signal_observations == ["source-silent"]
    replay = verify_beat_analysis(result.root / "beats.json", tmp_path / "replay")
    assert len(calls) == 2 and replay.saved == result
    assert replay.writer_eligibility == "blocked"
    assert capture_stream_input(source) == before


def test_changed_derived_peaks_cannot_pass_with_current_hashes(protocol, tmp_path: Path) -> None:
    _, decode, backend, _ = protocol
    result = analyze_beats(decode, backend, tmp_path / "candidate")
    result.beats.clear()
    path = result.root / "beats.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_beat_analysis(path, tmp_path / "replay")
    assert not (tmp_path / "replay/replay.json").exists()


def test_cancelled_candidate_does_not_publish(protocol, tmp_path: Path) -> None:
    from suno2flp.core.audio_decode import DecodeCancelled

    _, decode, backend, _ = protocol
    output = tmp_path / "cancelled"
    with pytest.raises(DecodeCancelled):
        analyze_beats(
            decode, backend, output, should_cancel=lambda: (output / "native/result.json").exists()
        )
    assert not (output / "beats.json").exists()


def test_full_coherent_native_rehash_still_requires_real_fresh_prediction(
    protocol, tmp_path: Path
) -> None:
    _, decode, backend, calls = protocol
    result = analyze_beats(decode, backend, tmp_path / "candidate")
    for name, frame in (("beat.f32", 1), ("chunk-0-beat.f32", 7)):
        path = result.root / "native" / name
        raw = bytearray(path.read_bytes())
        struct.pack_into("<f", raw, frame * 4, 2.0)
        path.write_bytes(raw)
        result.native.files[name].sha256 = hashlib.sha256(raw).hexdigest()
    (result.root / "native/result.json").write_text(
        result.native.model_dump_json(), encoding="utf-8"
    )
    result.native_witnesses = capture_file_tree(result.root / "native")
    path = result.root / "beats.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="Fresh native"):
        verify_beat_analysis(path, tmp_path / "replay")
    assert len(calls) == 2
    assert not (tmp_path / "replay/replay.json").exists()
