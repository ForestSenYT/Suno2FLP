"""Original fixed PCM fixtures; rhythm probe success is not musical quality."""

import struct

from suno2flp.core.beat_native import BeatProbe
from suno2flp.core.note_scoring import ScoringRecipe


class BeatRuntimeProbe(BeatProbe):
    recipe: ScoringRecipe


BEAT_FIXTURES = {
    "silence": (2049, 44100, 2),
    "impulses": (12347, 11025, 1),
    "stereo-cancellation": (48001, 48000, 2),
    "overlap-tail": (240081, 8000, 2),
}


def beat_fixture_wave(name: str) -> bytes:
    frames, rate, channels = BEAT_FIXTURES[name]
    size = frames * channels * 8
    output = bytearray(
        struct.pack(
            "<4sI4s4sIHHIIHHH4sII4sI",
            b"RIFF",
            50 + size,
            b"WAVE",
            b"fmt ",
            18,
            3,
            channels,
            rate,
            rate * channels * 8,
            channels * 8,
            64,
            0,
            b"fact",
            4,
            frames,
            b"data",
            size,
        )
    )
    values: tuple[float, ...]
    for frame in range(frames):
        if name == "silence":
            values = (0.0, 0.0)
        elif name == "impulses":
            values = (0.5 if frame in (0, 6000, frames - 1) else 0.0,)
        elif name == "stereo-cancellation":
            value = ((frame * 37) % 1024 - 512) / 2048
            values = (value, -value)
        else:
            values = (((frame * 37) % 1024 - 512) / 2048, ((frame * 71 + 19) % 2048 - 1024) / 4096)
        output.extend(struct.pack("<" + "d" * channels, *values))
    return bytes(output)
