"""Opt-in original tone and tail test; the application never installs model dependencies."""

import json
import math
import os
import struct
import wave
from pathlib import Path

import pytest

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.core.yourmt3 import FrameInterval
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.pipeline.yourmt3 import transcribe_yourmt3
from suno2flp.validator.yourmt3 import verify_yourmt3


@pytest.mark.external
def test_fixed_cpu_real_handshake_tail_tokens_repeat_and_source_preservation(tmp_path):
    value = os.environ.get("SUNO2FLP_YOURMT3_BACKEND")
    if not value:
        pytest.skip("Set SUNO2FLP_YOURMT3_BACKEND to a separately provisioned fixed CPU backend")
    backend = Path(value)
    if not (backend / "backend.json").is_file():
        pytest.skip("Fixed YourMT3 backend.json prerequisite is missing")
    # 32768 model frames: the second window contains exactly one real sample.
    rate = 48000
    frames = 98304
    source = tmp_path / "original tone.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, rate, frames, "NONE", "not compressed"))
        stream.writeframes(
            b"".join(
                struct.pack("<h", round(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(frames)
            )
        )
    before = capture_stream_input(source)
    decode_pcm_wave(source, tmp_path / "decode")
    intervals = [FrameInterval(start_frame=0, end_frame=frames)]
    first = transcribe_yourmt3(
        tmp_path / "decode/decode.json", backend, tmp_path / "first", intervals
    )
    second = transcribe_yourmt3(
        tmp_path / "decode/decode.json", backend, tmp_path / "second", intervals
    )
    a = json.loads(first.raw.path.read_bytes())
    b = json.loads(second.raw.path.read_bytes())
    assert a["windows"] == b["windows"]
    assert a["notes"] == b["notes"]
    assert a["windows"][-1]["valid_frames"] == 1
    assert len(a["windows"]) == 2
    assert first == verify_yourmt3(first.root / "yourmt3.json")
    assert first.writer_eligibility == "blocked"
    assert capture_stream_input(source) == before
