"""Independent integer IEEE oracle for the complete derived waveform relation."""

import struct
import time
from collections.abc import Callable

from suno2flp.core.audio_decode import check_decode_request
from suno2flp.core.offline_files import verify_inputs
from suno2flp.core.offline_models import FileIdentity


def _binary64(bits: int) -> int:
    sign = (bits >> 31) << 63
    exponent, fraction = (bits >> 23) & 255, bits & 0x7FFFFF
    if exponent == 255:
        raise ValueError("Estimated source contains a nonfinite sample")
    if exponent:
        return sign | ((exponent + 896) << 52) | (fraction << 29)
    if not fraction:
        return sign
    leading = fraction.bit_length() - 1
    return sign | ((leading + 874) << 52) | ((fraction - (1 << leading)) << (52 - leading))


def verify_stem_wave(
    source: FileIdentity,
    pcm: FileIdentity,
    *,
    frames: int,
    sample_rate: int,
    channels: int,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """No producer helper or floating-point conversion is used to derive expected bits."""
    if (
        any(type(value) is not int for value in (frames, sample_rate, channels))
        or not 8000 <= sample_rate <= 192000
        or channels not in (1, 2)
        or not 0 < frames <= sample_rate * 600
        or source.path == pcm.path
    ):
        raise ValueError("Invalid derived source clock or waveform alias")
    deadline = time.monotonic() + 300
    check_decode_request(should_cancel, deadline)
    verify_inputs([source, pcm])
    with source.path.open("rb") as original, pcm.path.open("rb") as widened:
        for stream, identity, width in ((original, source, 4), (widened, pcm, 8)):
            size = frames * channels * width
            raw = stream.read(58)
            if len(raw) != 58 or identity.size_bytes != 58 + size:
                raise ValueError("Incomplete canonical estimated waveform")
            fields = struct.unpack("<4sI4s4sIHHIIHHH4sII4sI", raw)
            if fields != (
                b"RIFF",
                50 + size,
                b"WAVE",
                b"fmt ",
                18,
                3,
                channels,
                sample_rate,
                sample_rate * channels * width,
                channels * width,
                width * 8,
                0,
                b"fact",
                4,
                frames,
                b"data",
                size,
            ):
                raise ValueError("Derived waveform header disagrees with original source clock")
        remaining = frames * channels
        while remaining:
            check_decode_request(should_cancel, deadline)
            count = min(4096, remaining)
            raw, actual = original.read(count * 4), widened.read(count * 8)
            if len(raw) != count * 4 or len(actual) != count * 8:
                raise ValueError("Complete estimated waveform was truncated")
            expected = b"".join(
                struct.pack("<Q", _binary64(value[0])) for value in struct.iter_unpack("<I", raw)
            )
            if expected != actual:
                raise ValueError("Derived samples do not preserve exact finite source bits")
            remaining -= count
        if original.read(1) or widened.read(1):
            raise ValueError("Estimated waveform contains an unrecorded tail")
    verify_inputs([source, pcm])
    check_decode_request(should_cancel, deadline)
