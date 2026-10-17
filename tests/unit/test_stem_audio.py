"""Exact representation widening, independently checked against IEEE sample bits."""

import importlib
import math
import struct

import pytest

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input


def header(frames, rate, channels, bits):
    width = channels * (bits // 8)
    size = frames * width
    return struct.pack(
        "<4sI4s4sIHHIIHHH4sII4sI",
        b"RIFF",
        size + 50,
        b"WAVE",
        b"fmt ",
        18,
        3,
        channels,
        rate,
        rate * width,
        width,
        bits,
        0,
        b"fact",
        4,
        frames,
        b"data",
        size,
    )


def services():
    return (
        importlib.import_module("suno2flp.importer.stem_audio"),
        importlib.import_module("suno2flp.validator.stem_audio"),
    )


@pytest.mark.parametrize("rate", [8000, 11025, 44100, 47999, 192000])
@pytest.mark.parametrize("channels", [1, 2])
def test_exact_finite_bits_channel_order_and_original_clock(tmp_path, rate, channels):
    producer, validator = services()
    bits = [
        0,
        0x80000000,
        1,
        0x807FFFFF,
        0x00800000,
        0x3F800000,
        0xBF000000,
        0x7F7FFFFF,
        0xFF7FFFFF,
        0x3F800001,
    ] * channels
    # Cross a streaming block boundary and retain the odd final sample/frame.
    bits = bits * 421 + bits[:channels]
    frames = len(bits) // channels
    source, output = tmp_path / "estimated.wav", tmp_path / "widened.wav"
    raw = b"".join(struct.pack("<I", value) for value in bits)
    source.write_bytes(header(frames, rate, channels, 32) + raw)
    before = capture_stream_input(source)
    result = producer.widen_stem_wave(
        source, output, frames=frames, sample_rate=rate, channels=channels
    )
    expected = header(frames, rate, channels, 64) + b"".join(
        struct.pack("<d", value[0]) for value in struct.iter_unpack("<f", raw)
    )
    assert output.read_bytes() == expected
    assert result == capture_stream_input(output)
    validator.verify_stem_wave(before, result, frames=frames, sample_rate=rate, channels=channels)
    assert capture_stream_input(source) == before


@pytest.mark.parametrize("kind", ["nan", "positive-inf", "negative-inf", "header", "tail", "short"])
def test_invalid_complete_input_fails_without_mutating_source(tmp_path, kind):
    producer, _ = services()
    source = tmp_path / "estimated.wav"
    raw = header(1, 44100, 1, 32) + struct.pack("<f", 0.5)
    if kind in {"nan", "positive-inf", "negative-inf"}:
        value = {"nan": math.nan, "positive-inf": math.inf, "negative-inf": -math.inf}[kind]
        raw = raw[:58] + struct.pack("<f", value)
    elif kind == "header":
        raw = raw[:20] + b"\x01\x00" + raw[22:]
    elif kind == "tail":
        raw += b"extra"
    else:
        raw = raw[:-1]
    source.write_bytes(raw)
    before = source.read_bytes()
    with pytest.raises(ValueError):
        producer.widen_stem_wave(
            source, tmp_path / "out.wav", frames=1, sample_rate=44100, channels=1
        )
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("frames", 0),
        ("frames", True),
        ("sample_rate", 7999),
        ("sample_rate", 192001),
        ("channels", 3),
        ("frames", 26460001),
    ],
)
def test_invalid_geometry_is_rejected_before_writes(tmp_path, field, value):
    producer, _ = services()
    source = tmp_path / "estimated.wav"
    source.write_bytes(header(1, 44100, 1, 32) + b"\0" * 4)
    kwargs = dict(frames=1, sample_rate=44100, channels=1)
    kwargs[field] = value
    with pytest.raises(ValueError):
        producer.widen_stem_wave(source, tmp_path / "out.wav", **kwargs)
    assert not (tmp_path / "out.wav").exists()


@pytest.mark.parametrize(
    "corruption", ["zero-sign", "channel-swap", "tail", "header", "changed-source"]
)
def test_independent_verifier_rejects_rehashed_widened_forgeries(tmp_path, corruption):
    producer, validator = services()
    source, output = tmp_path / "source.wav", tmp_path / "output.wav"
    source.write_bytes(header(2, 47999, 2, 32) + struct.pack("<ffff", -0.0, 0.5, 1.0, -2.0))
    original = capture_stream_input(source)
    producer.widen_stem_wave(source, output, frames=2, sample_rate=47999, channels=2)
    data = bytearray(output.read_bytes())
    if corruption == "zero-sign":
        struct.pack_into("<d", data, 58, 0.0)
    elif corruption == "channel-swap":
        data[58:74] = data[66:74] + data[58:66]
    elif corruption == "tail":
        data.extend(b"extra")
    elif corruption == "header":
        struct.pack_into("<I", data, 24, 48000)
    else:
        source.write_bytes(source.read_bytes()[:-4] + struct.pack("<f", 3.0))
    output.write_bytes(data)
    with pytest.raises((ValueError, Suno2FLPError)) as failure:
        validator.verify_stem_wave(
            original, capture_stream_input(output), frames=2, sample_rate=47999, channels=2
        )
    assert str(failure.value)


def test_exclusive_output_and_cancellation(tmp_path):
    producer, validator = services()
    source, output = tmp_path / "source.wav", tmp_path / "output.wav"
    source.write_bytes(header(1, 44100, 1, 32) + b"\0" * 4)
    before = capture_stream_input(source)
    with pytest.raises((ValueError, FileExistsError)):
        producer.widen_stem_wave(source, source, frames=1, sample_rate=44100, channels=1)
    with pytest.raises(DecodeCancelled):
        producer.widen_stem_wave(
            source, output, frames=1, sample_rate=44100, channels=1, should_cancel=lambda: True
        )
    assert not output.exists()
    producer.widen_stem_wave(source, output, frames=1, sample_rate=44100, channels=1)
    with pytest.raises((ValueError, FileExistsError)):
        producer.widen_stem_wave(source, output, frames=1, sample_rate=44100, channels=1)
    with pytest.raises(DecodeCancelled):
        validator.verify_stem_wave(
            before,
            capture_stream_input(output),
            frames=1,
            sample_rate=44100,
            channels=1,
            should_cancel=lambda: True,
        )
    assert capture_stream_input(source) == before
