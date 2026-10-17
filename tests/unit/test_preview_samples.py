"""Original finite one-shot percussion; no factory asset/dependency."""

import io
import wave

import pytest

from suno2flp.core.audio_flp import DRUM_PREVIEW_KEYS
from suno2flp.flp_builder.preview_samples import percussion_sample


def test_samples_are_repeatable_finite_pcm_with_complete_release():
    results = []
    for key in DRUM_PREVIEW_KEYS:
        raw = percussion_sample(key)
        assert raw == percussion_sample(key)
        with wave.open(io.BytesIO(raw)) as stream:
            assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) == (
                1,
                2,
                44100,
            )
            assert 0 < stream.getnframes() <= 2 * 44100
            pcm = stream.readframes(stream.getnframes())
            assert any(pcm) and pcm[-2:] == b"\0\0"
        results.append(raw)
    assert len(set(results)) == 9
    with pytest.raises(ValueError):
        percussion_sample(35)
