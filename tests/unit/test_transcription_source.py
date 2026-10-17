"""Second consumer of fresh decoding evidence, without a native model dependency."""

import wave
from pathlib import Path

import pytest

from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.validator.transcription_source import verified_transcription_source


def test_pcm_clock_and_all_source_witnesses_are_retained(tmp_path: Path) -> None:
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 2000)
    output = tmp_path / "decoded"
    report = decode_pcm_wave(source, output)
    result = verified_transcription_source(output / "decode.json")
    assert (result.frames, result.sample_rate, result.channels) == (2000, 8000, 1)
    assert result.pcm == report.pcm
    assert source.resolve() in {w.path for w in result.dependencies}
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(Exception, match="changed|mismatch|size"):
        verified_transcription_source(output / "decode.json")
