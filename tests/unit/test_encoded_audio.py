"""Original container/bitstream fixtures, independent checksums and no native codec."""

import hashlib
import struct

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input


def inspect(path, **kwargs):
    from suno2flp.importer.encoded_audio import inspect_encoded_audio

    return inspect_encoded_audio(path, **kwargs)


def crc(raw, bits=16, reflected=False):
    # Deliberately bit-at-a-time fixture oracle; production must not import it.
    value = 0
    for byte in raw:
        if reflected:
            value ^= byte
            for _ in range(8):
                value = (value >> 1) ^ (0xA001 if value & 1 else 0)
        else:
            value ^= byte << (bits - 8)
            for _ in range(8):
                value = (
                    (value << 1)
                    ^ ((7 if bits == 8 else 0x8005) if value & (1 << (bits - 1)) else 0)
                ) & ((1 << bits) - 1)
    return value


def packed(bits):
    padded = bits + "0" * (-len(bits) % 8)
    return int(padded, 2).to_bytes(len(padded) // 8, "big") if padded else b""


def flac_frame(number=0, frames=16, channels=1, kind="constant", variable=False):
    header = b"\xff" + bytes(
        [0xF9 if variable else 0xF8, 0x60, (channels - 1) * 16 + 8, number, frames - 1]
    )
    header += bytes([crc(header, bits=8)])
    body = ""
    for _ in range(channels):
        if kind == "constant":
            body += "00000000" + "0" * 16
        elif kind == "verbatim":
            body += "00000010" + "0" * (frames * 16)
        elif kind == "wasted":
            body += "00000011" + "01" + "0" * (frames * 14)
        elif kind in ("fixed", "rice2", "escape"):
            body += "00010000"  # fixed predictor, order zero
            body += "01" if kind == "rice2" else "00"
            body += "0000"  # one partition
            if kind == "escape":
                body += "1111" + "00000"  # zero-bit unencoded residuals
            else:
                body += ("00000" if kind == "rice2" else "0000") + "1" * frames
        elif kind == "lpc":
            body += "01000000" + "0" * 16  # LPC order1, warmup
            body += "0000" + "00000" + "0"  # precision1, shift0, coefficient0
            body += "00" + "0000" + "0000" + "1" * (frames - 1)
        elif kind == "bad-predictor":
            body += "01111110"  # order32 cannot fit sixteen samples
        else:
            raise AssertionError(kind)
    raw = header + packed(body)
    return raw + struct.pack(">H", crc(raw))


def flac_file(frames, *, channels=1, count=None, md5=None, rate=8000, depth=16, metadata=False):
    total = count if count is not None else len(frames) * 16
    stream = struct.pack(">HH", 16, 16) + b"\0" * 6
    stream += ((rate << 44) | ((channels - 1) << 41) | ((depth - 1) << 36) | total).to_bytes(
        8, "big"
    )
    stream += md5 if md5 is not None else hashlib.md5(b"\0" * (total * channels * 2)).digest()
    header = b"fLaC" + bytes([0 if metadata else 128, 0, 0, 34]) + stream
    if metadata:
        header += b"\x81\0\0\x01\0"  # final padding metadata
    return header + b"".join(frames)


@pytest.mark.parametrize(
    "kind", ["constant", "verbatim", "wasted", "fixed", "rice2", "escape", "lpc"]
)
@pytest.mark.parametrize("channels", [1, 2])
def test_flac_complete_subframe_coverage_preserves_clock_and_raw_provenance(
    tmp_path, kind, channels
):
    source = tmp_path / "原创 source.flac"
    source.write_bytes(
        flac_file([flac_frame(channels=channels, kind=kind)], channels=channels, metadata=True)
    )
    before = capture_stream_input(source)
    result = inspect(source)
    assert result.source == before and result.codec == "FLAC"
    assert (result.frames, result.channels, result.sample_rate) == (16, channels, 8000)
    assert result.frame_count == 1 and result.data_end == before.size_bytes
    assert result.duration_microseconds.model_dump() == {"numerator": 2000, "denominator": 1}
    assert result.flac.bits_per_sample == 16 and len(result.flac.raw_streaminfo_hex) == 68
    assert len(result.metadata) == 2 and result.metadata[1].offset == 42
    assert result.frame_headers_sha256 and result.decode_status == "not_performed"
    assert result.writer_eligibility == "blocked"
    assert capture_stream_input(source) == before


def test_flac_variable_sample_number_and_short_final_frame_are_exact(tmp_path):
    source = tmp_path / "variable.flac"
    source.write_bytes(
        flac_file(
            [flac_frame(variable=True), flac_frame(number=16, frames=8, variable=True)], count=24
        )
    )
    result = inspect(source)
    assert result.frames == 24 and result.frame_count == 2
    assert result.duration_microseconds.numerator == 3000


@pytest.mark.parametrize(
    "damage",
    ["tail", "concat", "truncated", "header-crc", "frame-crc", "number", "count", "predictor"],
)
def test_flac_native_success_cannot_hide_incomplete_or_inconsistent_bitstreams(tmp_path, damage):
    frame = flac_frame(
        number=1 if damage == "number" else 0,
        kind="bad-predictor" if damage == "predictor" else "constant",
    )
    raw = flac_file([frame], count=17 if damage == "count" else None)
    if damage == "tail":
        raw += b"junk"
    if damage == "concat":
        raw += raw
    if damage == "truncated":
        raw = raw[:-1]
    if damage == "header-crc":
        raw = raw[:48] + bytes([raw[48] ^ 1]) + raw[49:]
    if damage == "frame-crc":
        raw = raw[:-1] + bytes([raw[-1] ^ 1])
    source = tmp_path / "bad.flac"
    source.write_bytes(raw)
    with pytest.raises(OfflineError) as error:
        inspect(source)
    assert not getattr(error.value, "blocked", False)


@pytest.mark.parametrize(
    "change", ["unknown-count", "unknown-md5", "depth", "channels", "duration"]
)
def test_flac_unqualified_or_over_budget_profiles_are_explicitly_blocked(tmp_path, change):
    options = {"count": 0} if change == "unknown-count" else {}
    if change == "unknown-md5":
        options["md5"] = b"\0" * 16
    if change == "depth":
        options["depth"] = 32
    if change == "channels":
        options["channels"] = 6
    if change == "duration":
        options["count"] = 8000 * 600 + 1
    source = tmp_path / "unsupported.flac"
    source.write_bytes(flac_file([flac_frame()], **options))
    with pytest.raises(OfflineError) as error:
        inspect(source)
    assert error.value.blocked


def mp3_file(rate=44100, channels=2, *, variable=False, id3=False):
    # Original structural frames; real codec integration uses its own encoded audio.
    if rate in (44100, 48000, 32000):
        version, rates, sizes, samples = 3, (44100, 48000, 32000), (417, 384, 576), 1152
    elif rate in (22050, 24000, 16000):
        version, rates, sizes, samples = 2, (22050, 24000, 16000), (261, 240, 360), 576
    else:
        version, rates, sizes, samples = 0, (11025, 12000, 8000), (522, 480, 720), 576
    index = rates.index(rate)
    header = bytes([255, 0xE3 | version << 3, 0x90 | index << 2, 192 if channels == 1 else 0])
    frame_size = sizes[index]
    music = header + b"\0" * (frame_size - 4)
    audio = music * 2
    first = bytearray(header + b"\0" * (frame_size - 4))
    xing = 4 + ((17 if channels == 1 else 32) if version == 3 else (9 if channels == 1 else 17))
    first[xing : xing + 4] = b"Xing" if variable else b"Info"
    first[xing + 4 : xing + 16] = struct.pack(">III", 15, 2, len(first) + len(audio))
    lame = xing + 120
    first[lame : lame + 9] = b"LAME3.100"
    first[lame + 9] = 4
    first[lame + 21 : lame + 24] = ((576 << 12) | 100).to_bytes(3, "big")
    first[lame + 28 : lame + 32] = struct.pack(">I", len(first) + len(audio))
    first[lame + 32 : lame + 34] = struct.pack(">H", crc(audio, reflected=True))
    first[lame + 34 : lame + 36] = struct.pack(">H", crc(first[: lame + 34], reflected=True))
    encoded = bytes(first) + audio
    if id3:
        encoded = b"ID3\x04\0\0\0\0\0\x04test" + encoded + b"TAG" + b"\0" * 125
    return encoded, samples * 2 - 676, lame


@pytest.mark.parametrize("rate", [8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000])
@pytest.mark.parametrize("channels", [1, 2])
def test_mp3_complete_frames_and_gapless_crc_preserve_presentation_clock(tmp_path, rate, channels):
    raw, expected, _ = mp3_file(rate, channels, variable=True, id3=True)
    source = tmp_path / "原创.mp3"
    source.write_bytes(raw)
    before = capture_stream_input(source)
    result = inspect(source)
    assert result.source == before and result.codec == "MP3"
    assert (result.sample_rate, result.channels, result.frames) == (rate, channels, expected)
    assert result.frame_count == 3 and result.mp3.audio_frames == 2
    assert (result.mp3.encoder_delay, result.mp3.encoder_padding) == (576, 100)
    assert result.data_offset == 14 and result.data_end == len(raw) - 128
    assert result.mp3.encoder_hex == b"LAME3.100".hex()
    assert result.mp3.music_crc16 == crc(raw[14 + (len(raw) - 142) // 3 : -128], reflected=True)
    assert capture_stream_input(source) == before


@pytest.mark.parametrize(
    "damage", ["truncated", "extra-frame", "frame-data", "tag-crc", "rate", "tail"]
)
def test_mp3_rejects_native_partial_success_and_encoded_payload_damage(tmp_path, damage):
    raw, _, lame = mp3_file()
    if damage == "truncated":
        raw = raw[:-1]
    if damage == "extra-frame":
        raw += raw[-417:]
    if damage == "frame-data":
        raw = raw[:-10] + bytes([raw[-10] ^ 1]) + raw[-9:]
    if damage == "tag-crc":
        raw = raw[: lame + 34] + b"\0\0" + raw[lame + 36 :]
    if damage == "rate":
        raw = raw[:419] + bytes([raw[419] ^ 4]) + raw[420:]
    if damage == "tail":
        raw += b"junk"
    source = tmp_path / "bad.mp3"
    source.write_bytes(raw)
    with pytest.raises(OfflineError) as error:
        inspect(source)
    assert not getattr(error.value, "blocked", False)


@pytest.mark.parametrize("change", ["missing-tag", "encoder", "revision"])
def test_mp3_unknown_gapless_semantics_never_guess_a_zero_origin(tmp_path, change):
    raw, _, lame = mp3_file()
    data = bytearray(raw)
    if change == "missing-tag":
        data[36:40] = b"\0" * 4
    if change == "encoder":
        data[lame : lame + 9] = b"Lavc60.00"
    if change == "revision":
        data[lame + 9] |= 16
    data[lame + 34 : lame + 36] = struct.pack(">H", crc(data[: lame + 34], reflected=True))
    source = tmp_path / "unknown.mp3"
    source.write_bytes(data)
    with pytest.raises(OfflineError) as error:
        inspect(source)
    assert error.value.blocked and error.value.code == "audio_timing_unavailable"


def test_cancellation_before_scanning_creates_nothing(tmp_path):
    source = tmp_path / "cancel.flac"
    source.write_bytes(flac_file([flac_frame()]))
    before = capture_stream_input(source)
    with pytest.raises(OfflineError) as error:
        inspect(source, should_cancel=lambda: True)
    assert error.value.code == "user_cancelled"
    assert capture_stream_input(source) == before


def test_fixture_checksums_match_published_polynomial_check_values():
    assert crc(b"123456789", bits=8) == 0xF4
    assert crc(b"123456789") == 0xFEE8
    assert crc(b"123456789", reflected=True) == 0xBB3D


def test_parser_budget_is_an_explicit_block_not_a_corruption_claim():
    from suno2flp.importer.flac_frames import _Bits

    for operation in (lambda bits: bits.read(17), lambda bits: bits.unary()):
        with pytest.raises(OfflineError) as error:
            operation(_Bits(b"\0" * 3, 0, 2))
        assert error.value.code == "audio_limits_exceeded" and error.value.blocked


def test_variable_bitrate_and_id3v24_footer_account_for_every_encoded_byte(tmp_path):
    raw, frames, lame = mp3_file(variable=True)
    data = bytearray(raw[:834] + b"\xff\xfb\xa0\0" + b"\0" * 518)
    data[48:52] = struct.pack(">I", len(data))
    data[lame + 28 : lame + 32] = struct.pack(">I", len(data))
    data[lame + 32 : lame + 34] = struct.pack(">H", crc(data[417:], reflected=True))
    data[lame + 34 : lame + 36] = struct.pack(">H", crc(data[: lame + 34], reflected=True))
    header = b"ID3\x04\0\x10\0\0\0\x03"
    path = tmp_path / "vbr.mp3"
    path.write_bytes(header + b"abc" + b"3DI" + header[3:] + data)
    result = inspect(path)
    assert result.frames == frames and result.frame_count == 3
    assert result.data_offset == 23 and result.data_end == path.stat().st_size


def test_protected_mpeg_frame_crcs_are_checked_including_lame_metadata_frame(tmp_path):
    raw, frames, lame = mp3_file()
    data = bytearray(raw)
    for start in (0, 417, 834):
        data[start + 1] &= 254
        value = 65535
        for byte in data[start + 2 : start + 4] + data[start + 6 : start + 38]:
            value ^= byte << 8
            for _ in range(8):
                value = ((value << 1) ^ (0x8005 if value & 32768 else 0)) & 65535
        data[start + 4 : start + 6] = struct.pack(">H", value)
    data[lame + 32 : lame + 34] = struct.pack(">H", crc(data[417:], reflected=True))
    data[lame + 34 : lame + 36] = struct.pack(">H", crc(data[: lame + 34], reflected=True))
    path = tmp_path / "protected.mp3"
    path.write_bytes(data)
    assert inspect(path).frames == frames
    data[417 + 10] ^= 1
    damaged = tmp_path / "bad-crc.mp3"
    damaged.write_bytes(data)
    with pytest.raises(OfflineError, match="protected header/side-info CRC"):
        inspect(damaged)
