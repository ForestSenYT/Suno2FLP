"""Original RIFF fixtures prove payload and timing checks, not header-only success."""

import hashlib
import struct

import pytest


def riff(chunks):
    body = b"WAVE" + b"".join(
        tag + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")
        for tag, data in chunks
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def pcm_format(channels=1, width=2, rate=8000, tag=1):
    return struct.pack(
        "<HHIIHH", tag, channels, rate, rate * channels * width, channels * width, width * 8
    )


def inspector():
    from suno2flp.importer.audio import inspect_audio

    return inspect_audio


def error():
    from suno2flp.core.audio_input import AudioPreflightError

    return AudioPreflightError


@pytest.mark.parametrize(
    "channels,width,frames,offset",
    [(1, 1, 4, 44), (1, 2, 4, 44), (1, 3, 4, 44), (1, 4, 4, 44), (2, 2, 2, 44)],
)
def test_pcm_payload_has_exact_frames_duration_hash_and_original_identity(
    tmp_path, channels, width, frames, offset
):
    data = b"\x01" * (channels * width * frames)
    raw = riff([(b"fmt ", pcm_format(channels, width)), (b"data", data)])
    path = tmp_path / "中文 source.wav"
    path.write_bytes(raw)
    before = path.stat()
    result = inspector()(path)
    assert (result.channels, result.sample_width_bytes, result.frames, result.data_offset) == (
        channels,
        width,
        frames,
        offset,
    )
    assert result.pcm_sha256 == hashlib.sha256(data).hexdigest()
    assert result.source.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.duration_microseconds.numerator == (500 if frames == 4 else 250)
    assert result.duration_microseconds.denominator == 1
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == before.st_mtime_ns


def test_unknown_odd_chunk_is_preserved_in_inventory_without_reading_as_pcm(tmp_path):
    path = tmp_path / "metadata.wav"
    path.write_bytes(riff([(b"JUNK", b"x"), (b"fmt ", pcm_format()), (b"data", b"\0" * 8)]))
    result = inspector()(path)
    assert result.data_offset == 54
    assert [(c.id_hex, c.offset, c.data_size) for c in result.chunks] == [
        ("4a554e4b", 12, 1),
        ("666d7420", 22, 16),
        ("64617461", 46, 8),
    ]


@pytest.mark.parametrize(
    "corruption",
    [
        "truncated",
        "riff_short",
        "chunk_long",
        "partial_frame",
        "missing_fmt",
        "missing_data",
        "duplicate_data",
        "bad_byte_rate",
        "bad_block_align",
        "empty",
    ],
)
def test_invalid_container_or_pcm_is_failed_not_accepted(tmp_path, corruption):
    fmt, data = pcm_format(), b"\0" * 8
    if corruption == "bad_byte_rate":
        fmt = fmt[:8] + struct.pack("<I", 7) + fmt[12:]
    if corruption == "bad_block_align":
        fmt = fmt[:12] + struct.pack("<H", 3) + fmt[14:]
    if corruption == "partial_frame":
        data = b"\0" * 7
    if corruption == "empty":
        data = b""
    chunks = [(b"fmt ", fmt), (b"data", data)]
    if corruption == "missing_fmt":
        chunks.pop(0)
    if corruption == "missing_data":
        chunks.pop()
    if corruption == "duplicate_data":
        chunks.append((b"data", data))
    raw = riff(chunks)
    if corruption == "truncated":
        raw = raw[:-1]
    if corruption == "riff_short":
        raw = raw[:4] + struct.pack("<I", 4) + raw[8:]
    if corruption == "chunk_long":
        raw = raw[:40] + struct.pack("<I", 9999) + raw[44:]
    path = tmp_path / "invalid.wav"
    path.write_bytes(raw)
    with pytest.raises(error()) as caught:
        inspector()(path)
    assert not caught.value.blocked


@pytest.mark.parametrize(
    "name,fmt,code",
    [
        ("input.mp3", pcm_format(), "audio_format_unavailable"),
        ("input.flac", pcm_format(), "audio_format_unavailable"),
        ("float.wav", pcm_format(tag=3), "audio_codec_unavailable"),
        ("extensible.wav", pcm_format(tag=65534), "audio_codec_unavailable"),
        ("surround.wav", pcm_format(channels=6), "audio_limits_exceeded"),
        ("fast.wav", pcm_format(rate=384000), "audio_limits_exceeded"),
    ],
)
def test_unavailable_profiles_are_explicitly_blocked(tmp_path, name, fmt, code):
    path = tmp_path / name
    path.write_bytes(riff([(b"fmt ", fmt), (b"data", b"\0" * 24)]))
    with pytest.raises(error()) as caught:
        inspector()(path)
    assert caught.value.blocked and caught.value.code == code


def test_duration_limit_is_checked_without_retiming_or_truncation(tmp_path):
    path = tmp_path / "long.wav"
    raw = riff([(b"fmt ", pcm_format(width=1)), (b"data", b"\0" * 4800001)])
    path.write_bytes(raw)
    with pytest.raises(error()) as caught:
        inspector()(path)
    assert caught.value.blocked and caught.value.code == "audio_limits_exceeded"
    assert path.stat().st_size == len(raw)


def test_changed_source_between_hash_and_parse_is_rejected(tmp_path, monkeypatch):
    from suno2flp.core.errors import OfflineError
    from suno2flp.importer import audio

    path = tmp_path / "changed.wav"
    path.write_bytes(riff([(b"fmt ", pcm_format()), (b"data", b"\0" * 8)]))
    original = audio.capture_stream_input

    def capture_then_change(path):
        identity = original(path)
        path.write_bytes(riff([(b"fmt ", pcm_format()), (b"data", b"\1" * 8)]))
        return identity

    monkeypatch.setattr(audio, "capture_stream_input", capture_then_change)
    with pytest.raises(OfflineError, match="offline_input_changed"):
        audio.inspect_audio(path)
