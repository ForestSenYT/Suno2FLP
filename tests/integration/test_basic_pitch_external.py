"""Opt-in actual fixed CPU inference; never runs by downloading from default CI."""

import math
import os
import platform
import struct
import sys
import wave
from pathlib import Path

import pytest

from suno2flp.core.offline_files import capture_stream_input
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.integrations.basic_pitch_backend import provision_basic_pitch, verify_basic_pitch
from suno2flp.pipeline.transcription import transcribe_audio
from suno2flp.validator.transcription import verify_transcription

pytestmark = pytest.mark.external


def test_actual_private_model_and_current_source_replay(tmp_path):
    artifacts = os.environ.get("SUNO2FLP_BASIC_PITCH_ARTIFACTS")
    if not artifacts:
        pytest.skip("Set SUNO2FLP_BASIC_PITCH_ARTIFACTS to the fixed locally audited artifacts")
    if sys.platform != "win32" or platform.python_version() != "3.11.16":
        pytest.skip("First model profile requires CPython3.11.16 Windows x64")
    backend = provision_basic_pitch(tmp_path / "backend", Path(artifacts))
    verify_basic_pitch(backend.root, tmp_path / "probe")
    source = tmp_path / "authored-440Hz.wav"
    rate = 22050
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes(
            b"".join(
                struct.pack("<h", round(0.25 * 32767 * math.sin(2 * math.pi * 440 * i / rate)))
                if 0.4 * rate <= i < 1.4 * rate
                else b"\0\0"
                for i in range(2 * rate)
            )
        )
    identity = capture_stream_input(source)
    decode_pcm_wave(source, tmp_path / "decode")
    candidate = transcribe_audio(
        tmp_path / "decode/decode.json", backend.root, tmp_path / "candidate"
    )
    assert candidate.result.windows == 2 and candidate.result.owned_rows == 174
    assert any(note.pitch == 69 for note in candidate.result.notes)
    assert (
        verify_transcription(tmp_path / "candidate/transcription.json", tmp_path / "replay")
        == candidate
    )
    assert capture_stream_input(source) == identity
    assert candidate.model_qualification == "not_assessed" and candidate.execution_allowed is False
