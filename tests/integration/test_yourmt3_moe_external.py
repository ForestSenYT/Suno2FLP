"""Opt-in fixed MoE native repetition and original-clock tail verification."""

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
from suno2flp.pipeline.yourmt3_moe import transcribe_yourmt3_moe
from suno2flp.validator.yourmt3_moe import verify_yourmt3_moe


@pytest.mark.external
def test_moe_real_cpu_repeat_thirteen_channels_and_one_frame_tail(tmp_path):
    value = os.environ.get("SUNO2FLP_YOURMT3_MOE_BACKEND")
    if not value:
        pytest.skip(
            "Set SUNO2FLP_YOURMT3_MOE_BACKEND to a separately provisioned fixed MoE backend"
        )
    backend = Path(value)
    if not (backend / "backend.json").is_file():
        pytest.skip("Fixed MoE backend.json prerequisite is missing")
    rate, frames = 48000, 98304
    source = tmp_path / "original MoE tone.wav"
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
    first = transcribe_yourmt3_moe(
        tmp_path / "decode/decode.json", backend, tmp_path / "first", intervals
    )
    second = transcribe_yourmt3_moe(
        tmp_path / "decode/decode.json", backend, tmp_path / "second", intervals
    )
    a, b = (json.loads(record.raw.path.read_bytes()) for record in (first, second))
    assert a["windows"] == b["windows"]
    assert a["channels"] == b["channels"]
    assert len(a["channels"]) == 13 and len(a["windows"]) == 2
    assert a["windows"][-1]["valid_frames"] == 1
    assert first == verify_yourmt3_moe(first.root / "yourmt3-moe.json")
    assert first.writer_eligibility == "blocked"
    assert capture_stream_input(source) == before
