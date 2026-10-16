"""Layer III audio main-data extents; no entropy decoding or silence concealment."""

from dataclasses import dataclass

from suno2flp.core.audio_input import AudioPreflightError


@dataclass
class MpegMainDataExtent:
    payload_bytes: int = 0
    previous_end_bits: int = 0

    def consume(self, side: bytes, *, channels: int, samples: int, payload_bytes: int) -> None:
        mpeg1 = samples == 1152
        expected = (17 if channels == 1 else 32) if mpeg1 else (9 if channels == 1 else 17)
        if (
            channels not in (1, 2)
            or samples not in (576, 1152)
            or len(side) != expected
            or payload_bytes < 0
        ):
            raise AudioPreflightError("audio_invalid", "Invalid MPEG audio side-information extent")
        pointer_bits = 9 if mpeg1 else 8
        private_bits = (5 if channels == 1 else 3) if mpeg1 else channels
        record_start = pointer_bits + private_bits + (4 * channels if mpeg1 else 0)
        record_bits = 59 if mpeg1 else 63
        records = (2 if mpeg1 else 1) * channels
        value = int.from_bytes(side, "big")
        total_bits = len(side) * 8
        backpointer = value >> (total_bits - pointer_bits)
        length = sum(
            (value >> (total_bits - record_start - index * record_bits - 12)) & 4095
            for index in range(records)
        )
        if backpointer > self.payload_bytes:
            raise AudioPreflightError(
                "audio_invalid", "MPEG audio reservoir references unavailable prior payload"
            )
        start = 8 * (self.payload_bytes - backpointer)
        end = start + length
        if start < self.previous_end_bits:
            raise AudioPreflightError(
                "audio_invalid", "MPEG main-data overlap reuses consumed audio bits"
            )
        if end > 8 * (self.payload_bytes + payload_bytes):
            raise AudioPreflightError(
                "audio_invalid", "MPEG main-data length exceeds available audio payload"
            )
        # Unused bytes/bits are legitimate ancillary data. Headers/CRC/side-info/Xing
        # never enter this logical audio-payload coordinate system.
        self.payload_bytes += payload_bytes
        self.previous_end_bits = end
