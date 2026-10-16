"""Authored PCM fixtures prove every sample and exact source clock, without a DAW."""

import hashlib
import json
import struct

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input


def decoder():
    from suno2flp.importer.pcm_decode import decode_pcm_wave

    return decode_pcm_wave


def verifier():
    from suno2flp.validator.pcm_decode import verify_pcm_decode

    return verify_pcm_decode


def original_wave(tmp_path, width=2, channels=1, samples=None, rate=44100):
    scale = 1 << (width * 8 - 1)
    values = samples if samples is not None else [-scale, -1, 0, 1, scale - 1, 0]
    payload = b"".join(
        (value + 128).to_bytes(1, "little")
        if width == 1
        else value.to_bytes(width, "little", signed=True)
        for value in values
    )
    fmt = struct.pack(
        "<HHIIHH", 1, channels, rate, rate * channels * width, channels * width, width * 8
    )
    chunks = [(b"JUNK", b"x"), (b"fmt ", fmt), (b"data", payload)]
    body = b"WAVE" + b"".join(
        tag + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")
        for tag, data in chunks
    )
    source = tmp_path / "原始 song.wav"
    source.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return source, values


@pytest.mark.parametrize("width", [1, 2, 3, 4])
@pytest.mark.parametrize("channels", [1, 2])
def test_decode_preserves_every_integer_sample_frame_channel_and_rational_clock(
    tmp_path, width, channels
):
    source, values = original_wave(tmp_path, width, channels)
    before = capture_stream_input(source)
    root = tmp_path / "新 decode"
    result = decoder()(source, root)
    report = root / "decode.json"
    assert result == verifier()(report)
    assert result.preflight.source == before
    assert result.preflight.frames == len(values) // channels
    assert result.preflight.sample_rate == 44100
    assert result.preflight.channels == channels
    assert result.preflight.sample_width_bytes == width
    assert result.frame_zero_source_frame == 0 and result.resampling == "none"
    assert result.duration_microseconds == result.preflight.duration_microseconds
    assert result.runtime.python_version and result.runtime.decoder.sha256
    assert result.runtime.contract.sha256
    assert result.runtime.executable.size_bytes > 0
    raw = result.pcm.path.read_bytes()
    floats = [item[0] for item in struct.iter_unpack("<d", raw[58:])]
    assert floats == [value / (1 << (8 * width - 1)) for value in values]
    assert result.samples_sha256 == hashlib.sha256(raw[58:]).hexdigest()
    assert result.pcm == capture_stream_input(root / "decoded.wav")
    assert result.writer_eligibility == "blocked" and result.musical_correctness == "not_assessed"
    assert capture_stream_input(source) == before
    assert sorted(p.name for p in root.iterdir()) == ["decode.json", "decoded.wav"]


def test_late_stereo_impulse_survives_block_boundaries_and_source_metadata_stays_intact(tmp_path):
    values = [0] * 40000
    values[-3] = -(1 << 31)
    values[-2] = (1 << 31) - 1
    source, _ = original_wave(tmp_path, 4, 2, values, rate=48000)
    result = decoder()(source, tmp_path / "decode")
    assert result.preflight.frames == 20000
    assert result.preflight.chunks[0].id_hex == "4a554e4b"
    assert verifier()(tmp_path / "decode/decode.json") == result
    assert struct.unpack("<ddd", result.pcm.path.read_bytes()[-24:]) == (
        -1.0,
        1 - 2**-31,
        0.0,
    )


def rehash_output(root):
    report = root / "decode.json"
    data = json.loads(report.read_bytes())
    pcm = root / "decoded.wav"
    data["pcm"] = capture_stream_input(pcm).model_dump(mode="json")
    data["samples_sha256"] = hashlib.sha256(pcm.read_bytes()[58:]).hexdigest()
    report.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("replacement", [0.5, float("nan"), float("inf"), -1.1, 1.0, 2**-20])
def test_independent_verification_refuses_forged_samples_even_after_rehash(tmp_path, replacement):
    source, _ = original_wave(tmp_path)
    root = tmp_path / "decode"
    decoder()(source, root)
    with (root / "decoded.wav").open("r+b") as stream:
        stream.seek(58)
        stream.write(struct.pack("<d", replacement))
    rehash_output(root)
    with pytest.raises(OfflineError, match="sample|Sample"):
        verifier()(root / "decode.json")


@pytest.mark.parametrize("change", ["truncated", "header", "runtime", "source", "duplicate"])
def test_complete_evidence_is_required_not_just_a_valid_report(tmp_path, change):
    source, _ = original_wave(tmp_path)
    root = tmp_path / "decode"
    decoder()(source, root)
    report = root / "decode.json"
    data = json.loads(report.read_bytes())
    if change in ("truncated", "header"):
        pcm = root / "decoded.wav"
        raw = pcm.read_bytes()
        pcm.write_bytes(raw[:-8] if change == "truncated" else b"FAIL" + raw[4:])
        rehash_output(root)
    elif change == "runtime":
        data["runtime"]["decoder"]["sha256"] = "0" * 64
        report.write_text(json.dumps(data), encoding="utf-8")
    elif change == "source":
        source.write_bytes(source.read_bytes() + b"changed")
    else:
        report.write_bytes(report.read_bytes()[:-2] + b', "schema_version": 1}')
    with pytest.raises((OfflineError, ValueError)):
        verifier()(report)


def test_existing_output_and_backend_destinations_are_never_overwritten(tmp_path):
    source, _ = original_wave(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "decoded.wav"
    sentinel.write_bytes(b"keep")
    with pytest.raises((OfflineError, OSError)):
        decoder()(source, existing)
    assert sentinel.read_bytes() == b"keep"
    (existing / "backend.json").write_text("{}")
    with pytest.raises(OfflineError):
        decoder()(source, existing / "new")
    assert not (existing / "new").exists()


def test_cancel_preserves_partial_candidate_and_retry_uses_new_directory(tmp_path):
    source, _ = original_wave(tmp_path, samples=[0] * 40000)
    before = capture_stream_input(source)
    count = 0

    def cancel_after_chunks():
        nonlocal count
        count += 1
        return count >= 4

    root = tmp_path / "cancelled"
    with pytest.raises(OfflineError) as caught:
        decoder()(source, root, should_cancel=cancel_after_chunks)
    assert caught.value.code == "user_cancelled"
    assert (root / "decoded.wav").exists() and not (root / "decode.json").exists()
    partial = capture_stream_input(root / "decoded.wav")
    result = decoder()(source, tmp_path / "retry")
    assert verifier()(tmp_path / "retry/decode.json") == result
    assert capture_stream_input(root / "decoded.wav") == partial
    assert capture_stream_input(source) == before


def test_cancel_before_work_does_not_create_output_and_verify_can_be_cancelled(tmp_path):
    source, _ = original_wave(tmp_path)
    root = tmp_path / "not-created"
    with pytest.raises(OfflineError) as caught:
        decoder()(source, root, should_cancel=lambda: True)
    assert caught.value.code == "user_cancelled" and not root.exists()
    decoder()(source, root)
    with pytest.raises(OfflineError) as caught:
        verifier()(root / "decode.json", should_cancel=lambda: True)
    assert caught.value.code == "user_cancelled"


def test_unsupported_or_malformed_source_never_produces_a_decoded_candidate(tmp_path):
    source = tmp_path / "unknown.mp3"
    source.write_bytes(b"unknown")
    with pytest.raises(OfflineError) as caught:
        decoder()(source, tmp_path / "decode")
    assert caught.value.code == "audio_format_unavailable"
    assert not (tmp_path / "decode").exists()


def test_forged_time_map_cannot_validate(tmp_path):
    from pydantic import ValidationError

    source, _ = original_wave(tmp_path)
    result = decoder()(source, tmp_path / "decode")
    for field, value in (
        ("frame_zero_source_frame", 1),
        ("duration_microseconds", {"numerator": 1, "denominator": 1}),
        ("resampling", "estimated"),
    ):
        raw = result.model_dump()
        raw[field] = value
        with pytest.raises(ValidationError):
            type(result).model_validate(raw)


@pytest.mark.parametrize("rate", [8000, 192000])
def test_supported_sample_rate_extremes_preserve_frame_zero_and_duration(tmp_path, rate):
    source, _ = original_wave(tmp_path, rate=rate)
    result = decoder()(source, tmp_path / "decode")
    assert result.preflight.sample_rate == rate
    assert verifier()(tmp_path / "decode/decode.json") == result


def test_unqualified_duration_is_rejected_before_output_creation(tmp_path):
    source, _ = original_wave(tmp_path, width=1, samples=[0] * (8000 * 600 + 1), rate=8000)
    with pytest.raises(OfflineError) as caught:
        decoder()(source, tmp_path / "decode")
    assert caught.value.code == "audio_limits_exceeded"
    assert not (tmp_path / "decode").exists()


def test_clock_budget_is_checked_between_actual_blocks(tmp_path, monkeypatch):
    from suno2flp.core import audio_decode

    source, _ = original_wave(tmp_path, samples=[0] * 40000)
    # Only the external clock changes; real file decoding still executes.
    ticks = iter([0, 0, 0, 301])
    monkeypatch.setattr(audio_decode.time, "monotonic", lambda: next(ticks, 301))
    with pytest.raises(OfflineError) as caught:
        decoder()(source, tmp_path / "decode")
    assert caught.value.code == "audio_decode_timeout"
    assert (tmp_path / "decode/decoded.wav").exists()
    assert not (tmp_path / "decode/decode.json").exists()


def test_report_budget_failure_preserves_candidate_without_publishing_report(tmp_path, monkeypatch):
    from suno2flp.importer import pcm_decode

    assert pcm_decode.MAX_PCM_REPORT_BYTES == 1024**2
    # Exercise real serialization against a smaller external resource budget.
    monkeypatch.setattr(pcm_decode, "MAX_PCM_REPORT_BYTES", 1024)
    source, _ = original_wave(tmp_path)
    before = capture_stream_input(source)
    with pytest.raises(OfflineError) as caught:
        decoder()(source, tmp_path / "decode")
    assert caught.value.code == "audio_limits_exceeded" and caught.value.blocked
    assert not (tmp_path / "decode/decode.json").exists()
    assert capture_stream_input(source) == before
