"""Request-only synthetic declarations never claim a real model handshake."""

import json
import os
from pathlib import Path

import pytest

from suno2flp.core.drum_runtime import DrumBackend
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.integrations.drum_backend import drum_request, verify_drum_request


@pytest.fixture
def request_data(tmp_path):
    path = tmp_path / "stereo.f32"
    path.write_bytes(b"\0" * (513 * 8))
    os.utime(path, ns=(0, 0))
    pcm = capture_stream_input(path)
    code = capture_stream_input(Path(__file__))
    record = DrumBackend(
        root=tmp_path / "unprovisioned",
        python=code,
        runtime=[],
        artifacts=[],
        adapters=[],
        payload={},
    )
    return record, pcm, tmp_path


def test_request_owns_complete_source_metadata(request_data):
    record, pcm, _ = request_data
    request = drum_request(record, pcm, 513)
    pcm.size_bytes += 1
    assert request["pcm"]["size_bytes"] == 513 * 8
    assert request["model_frames"] == 513


@pytest.mark.parametrize("frames", [True, 512, 514, 26460001])
def test_bad_model_geometry_never_becomes_a_request(request_data, frames):
    record, pcm, _ = request_data
    with pytest.raises(ValueError):
        drum_request(record, pcm, frames)


@pytest.mark.parametrize(
    "change", ["source", "frames", "packages", "unknown", "nested_boolean", "duplicate"]
)
def test_saved_request_requires_exact_types_keys_and_identity(request_data, change):
    record, pcm, attempt = request_data
    expected = drum_request(record, pcm, 513)
    if change == "source":
        expected["pcm"]["sha256"] = "0" * 64
    elif change == "frames":
        expected["model_frames"] = 513.0
    elif change == "packages":
        expected["packages"] = "elsewhere"
    elif change == "unknown":
        expected["extra"] = True
    elif change == "nested_boolean":
        assert pcm.mtime_ns == 0
        expected["pcm"]["mtime_ns"] = False
    raw = json.dumps(expected)
    if change == "duplicate":
        raw = raw.replace('"model_frames": 513', '"model_frames": 513, "model_frames": 513')
    (attempt / "request.json").write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError):
        verify_drum_request(record, attempt, pcm, 513)
