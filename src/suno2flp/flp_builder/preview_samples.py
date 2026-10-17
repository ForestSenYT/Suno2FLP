"""Original approximate one-shot voices; deterministic within the captured runtime."""

import math
import struct
import wave
from io import BytesIO

from suno2flp.core.audio_flp import DRUM_PREVIEW_KEYS


def percussion_sample(key: int) -> bytes:
    if key not in DRUM_PREVIEW_KEYS:
        raise ValueError("Use one of the nine declared preview percussion classes")
    duration = {49: 1.2, 51: 1.2, 42: 0.12, 46: 0.6, 36: 0.6, 38: 0.35, 43: 0.5, 48: 0.4, 47: 0.45}[
        key
    ]
    count = round(duration * 44100)
    state = key + 1
    previous = 0.0
    samples = []
    for j in range(count):
        t = j / 44100
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        noise = (state >> 8) / 8388607.5 - 1
        high = (noise - previous) * 0.5
        previous = noise
        if key == 36:
            phase = 2 * math.pi * (45 * t + 105 * 0.025 * (1 - math.exp(-t / 0.025)))
            value = math.sin(phase) * math.exp(-12 * t) + 0.12 * noise * math.exp(-180 * t)
        elif key == 38:
            value = 0.65 * high * math.exp(-20 * t) + 0.35 * math.sin(
                2 * math.pi * 190 * t
            ) * math.exp(-18 * t)
        elif key in (43, 48, 47):
            frequency = {43: 116, 48: 190, 47: 150}[key]
            value = (math.sin(2 * math.pi * frequency * t) + 0.15 * noise) * math.exp(-13 * t)
        else:
            metal = sum(math.sin(2 * math.pi * f * t) for f in (590, 845, 1370, 2130)) / 4
            decay = {49: 7, 51: 5, 42: 60, 46: 12}[key]
            value = (0.65 * high + 0.35 * metal) * math.exp(-decay * t)
        envelope = min(1, j / 40, (count - 1 - j) / 220)
        samples.append(round(max(-1, min(1, value * envelope)) * 16000))
    result = BytesIO()
    with wave.open(result, "wb") as out:
        out.setparams((1, 2, 44100, count, "NONE", "not compressed"))
        out.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return result.getvalue()
