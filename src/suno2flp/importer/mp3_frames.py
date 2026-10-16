"""Complete MPEG Layer III frame coverage and qualified LAME gapless/tag checks."""

import hashlib
import struct
from collections.abc import Callable
from fractions import Fraction
from typing import Literal, NamedTuple, NoReturn

from suno2flp.core.audio_input import AudioPreflightError
from suno2flp.core.encoded_audio import EncodedAudioInventory, EncodedRegion, Mp3GaplessInfo
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.performance import RationalTime
from suno2flp.importer.encoded_checksums import lame_crc16, mpeg_crc16
from suno2flp.importer.mpeg_side_info import MpegMainDataExtent


def _invalid(message: str) -> NoReturn:
    raise AudioPreflightError("audio_invalid", message)


def _timing(message: str) -> NoReturn:
    raise AudioPreflightError("audio_timing_unavailable", message, blocked=True)


class _Header(NamedTuple):
    rate: int
    channels: int
    samples: Literal[576, 1152]
    size: int
    side: int


def _header(raw: bytes, offset: int, end: int) -> _Header:
    if offset + 4 > end:
        _invalid("Truncated MPEG frame header/trailing bytes")
    a, b, c, d = raw[offset : offset + 4]
    version, layer, bitrate, rate_index = (b >> 3) & 3, (b >> 1) & 3, c >> 4, (c >> 2) & 3
    if (
        a != 255
        or b & 224 != 224
        or version == 1
        or layer == 0
        or bitrate == 15
        or rate_index == 3
        or d & 3 == 2
    ):
        _invalid("Invalid MPEG sync or reserved frame header")
    if layer != 1 or bitrate == 0:
        raise AudioPreflightError(
            "audio_codec_unavailable", "Only non-free-format Layer III is qualified", blocked=True
        )
    rate = (44100, 48000, 32000)[rate_index] // (1 if version == 3 else 2 if version == 2 else 4)
    channels = 1 if d >> 6 == 3 else 2
    rates = (
        (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
        if version == 3
        else (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
    )
    size = (144000 if version == 3 else 72000) * rates[bitrate] // rate + ((c >> 1) & 1)
    side = (17 if channels == 1 else 32) if version == 3 else (9 if channels == 1 else 17)
    protected = b & 1 == 0
    if size < 4 + 2 * protected + side or offset + size > end:
        _invalid("Truncated or undersized MPEG frame")
    if protected:
        expected = int.from_bytes(raw[offset + 4 : offset + 6], "big")
        if (
            mpeg_crc16(raw[offset + 2 : offset + 4] + raw[offset + 6 : offset + 6 + side])
            != expected
        ):
            _invalid("MPEG protected header/side-info CRC mismatch")
    return _Header(rate, channels, 1152 if version == 3 else 576, size, side)


def _region(raw: bytes, kind: str, start: int, end: int) -> EncodedRegion:
    return EncodedRegion(
        kind=kind,
        offset=start,
        size_bytes=end - start,
        sha256=hashlib.sha256(memoryview(raw)[start:end]).hexdigest(),
    )


def scan_mp3(raw: bytes, source: FileIdentity, check: Callable[[], None]) -> EncodedAudioInventory:
    offset, end = 0, len(raw)
    metadata = []
    if raw.startswith(b"ID3"):
        if len(raw) < 10 or raw[3] == 255 or raw[4] == 255 or any(b & 128 for b in raw[6:10]):
            _invalid("Malformed complete ID3v2 header")
        if raw[3] not in (3, 4):
            raise AudioPreflightError(
                "audio_format_unavailable", "ID3v2 version is not qualified", blocked=True
            )
        if raw[5] & (31 if raw[3] == 3 else 15):
            _invalid("Reserved ID3v2 header flags")
        size = sum(value << (7 * (3 - index)) for index, value in enumerate(raw[6:10]))
        footer = raw[3] == 4 and bool(raw[5] & 16)
        offset = 10 + size + (10 if footer else 0)
        if offset > end or (footer and raw[offset - 10 : offset] != b"3DI" + raw[3:10]):
            _invalid("ID3v2 size/footer exceeds or contradicts the original file")
        metadata.append(_region(raw, "id3v2", 0, offset))
    if end >= 128 and raw[end - 128 : end - 125] == b"TAG":
        metadata.append(_region(raw, "id3v1", end - 128, end))
        end -= 128
    start = offset
    first = _header(raw, start, end)
    # LAME intentionally places Xing at this offset even with MPEG CRC protection.
    xing = start + 4 + first.side
    if raw[xing : xing + 4] not in (b"Xing", b"Info"):
        _timing("A complete Xing/Info gapless timing declaration is required")
    if xing + 8 > start + first.size:
        _invalid("Truncated Xing flags")
    flags = int.from_bytes(raw[xing + 4 : xing + 8], "big")
    if flags & ~15 or flags & 3 != 3:
        _timing("Xing frame/byte counts and known flags are required")
    position = xing + 8
    audio_frames = int.from_bytes(raw[position : position + 4], "big")
    encoded_bytes = int.from_bytes(raw[position + 4 : position + 8], "big")
    position += 8 + (100 if flags & 4 else 0) + (4 if flags & 8 else 0)
    lame = position
    if lame + 36 > start + first.size:
        _invalid("Truncated complete LAME gapless extension")
    if raw[lame : lame + 4] != b"LAME" or raw[lame + 9] >> 4:
        _timing("Only the qualified LAME revision-zero gapless extension is supported")
    trim = int.from_bytes(raw[lame + 21 : lame + 24], "big")
    delay, padding = trim >> 12, trim & 4095
    if delay > 3000 or padding > 3000:
        _timing("LAME encoder delay/padding is outside the qualified range")
    expected_tag_crc = int.from_bytes(raw[lame + 34 : lame + 36], "big")
    if lame_crc16(raw[start : lame + 34]) != expected_tag_crc:
        _invalid("LAME complete tag CRC mismatch")
    if (
        encoded_bytes != end - start
        or int.from_bytes(raw[lame + 28 : lame + 32], "big") != encoded_bytes
    ):
        _invalid("Xing/LAME declared stream bytes disagree with the complete source")
    frames = audio_frames * first.samples - delay - padding
    if audio_frames <= 0 or frames <= 0:
        _invalid("LAME trimming removes all declared audio")
    if frames > first.rate * 600:
        raise AudioPreflightError(
            "audio_limits_exceeded", "Audio exceeds ten minutes", blocked=True
        )
    digest = hashlib.sha256()
    side_digest = hashlib.sha256()
    reservoir = MpegMainDataExtent()
    music_crc, count = 0, 0
    metadata.append(_region(raw, "xing-lame-frame", start, start + first.size))
    while offset < end:
        check()
        header = _header(raw, offset, end)
        if header[:3] != first[:3]:
            _invalid("Changing MPEG sample rate/channel/version configuration")
        digest.update(struct.pack("<QQ", offset, header.size) + raw[offset : offset + 4])
        if count:
            crc_bytes = 0 if raw[offset + 1] & 1 else 2
            side_start = offset + 4 + crc_bytes
            side = raw[side_start : side_start + header.side]
            reservoir.consume(
                side,
                channels=header.channels,
                samples=header.samples,
                payload_bytes=header.size - 4 - crc_bytes - header.side,
            )
            side_digest.update(struct.pack("<QQ", offset, header.size) + side)
            music_crc = lame_crc16(raw[offset : offset + header.size], music_crc)
        count += 1
        offset += header.size
        if count > audio_frames + 1:
            _invalid("More MPEG frames than declared by Xing")
    if count != audio_frames + 1:
        _invalid("Incomplete MPEG frame coverage/count")
    expected_music_crc = int.from_bytes(raw[lame + 32 : lame + 34], "big")
    if music_crc != expected_music_crc:
        _invalid("LAME complete encoded music CRC mismatch")
    return EncodedAudioInventory(
        source=source,
        codec="MP3",
        sample_rate=first.rate,
        channels=first.channels,
        frames=frames,
        frame_count=count,
        data_offset=start,
        data_end=end,
        frame_headers_sha256=digest.hexdigest(),
        metadata=metadata,
        mp3=Mp3GaplessInfo(
            side_info_sha256=side_digest.hexdigest(),
            raw_tag_hex=raw[xing : lame + 36].hex(),
            tag_offset=xing,
            encoder_hex=raw[lame : lame + 9].hex(),
            encoder_delay=delay,
            encoder_padding=padding,
            audio_frames=audio_frames,
            samples_per_frame=first.samples,
            encoded_bytes=encoded_bytes,
            music_crc16=expected_music_crc,
            tag_crc16=expected_tag_crc,
        ),
        duration_microseconds=RationalTime.exact(Fraction(frames * 1_000_000, first.rate)),
    )
