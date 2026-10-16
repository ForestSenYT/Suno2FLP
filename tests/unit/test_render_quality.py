import json
import math
import struct
import wave
from pathlib import Path

import pytest
from typer.testing import CliRunner

from suno2flp.cli import app
from suno2flp.core.errors import Suno2FLPError


def wav(path, samples, *, width=2, channels=1, rate=8000):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(width)
        stream.setframerate(rate)
        stream.writeframes(
            b"".join(
                (sample + 128).to_bytes(1, "little")
                if width == 1
                else sample.to_bytes(width, "little", signed=True)
                for sample in samples
            )
        )
    return path


def compare(reference, candidate, **kwargs):
    from suno2flp.validator.renders import compare_renders

    return compare_renders(reference, candidate, **kwargs)


def test_measurements_without_threshold_do_not_claim_audible_acceptance(tmp_path):
    reference = wav(tmp_path / "ref.wav", [0, 0])
    candidate = wav(tmp_path / "candidate.wav", [16384, -16384])
    report = compare(reference, candidate)
    assert report.valid and report.within_tolerance is None and report.samples_identical is False
    assert report.rms_difference == 0.5 and report.max_abs_difference == 0.5
    assert report.reference_rms == 0 and report.candidate_rms == 0.5
    assert report.compared_samples == 2 and report.frames_reference == 2
    assert report.sample_rate == 8000 and report.channels == 1
    assert report.host_compatibility == "unverified" and report.audible_acceptance == "unverified"
    assert not report.execution_allowed


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_supported_integer_widths_are_normalized_without_shifting_time(tmp_path, width):
    half = 2 ** (8 * width - 2)
    reference = wav(tmp_path / "ref.wav", [0, 0], width=width)
    candidate = wav(tmp_path / "candidate.wav", [half, -half], width=width)
    result = compare(reference, candidate)
    assert result.valid and result.sample_width_bytes == width
    assert result.rms_difference == 0.5 and result.compared_samples == 2


@pytest.mark.parametrize("limit,within", [(0.49, False), (0.5, True), (0.51, True)])
def test_only_explicit_numerical_tolerance_produces_tolerance_decision(tmp_path, limit, within):
    reference = wav(tmp_path / "ref.wav", [0, 0])
    candidate = wav(tmp_path / "candidate.wav", [16384, -16384])
    result = compare(reference, candidate, max_rms_error=limit)
    assert result.within_tolerance is within and result.valid is within
    assert result.audible_acceptance == "unverified"


def test_identical_stereo_and_full_scale_counts_are_streamed_read_only(tmp_path, monkeypatch):
    reference = wav(tmp_path / "ref.wav", [-32768, 32767] * 10000, channels=2)
    candidate = wav(tmp_path / "candidate.wav", [-32768, 32767] * 10000, channels=2)
    original_read = Path.read_bytes
    before = [(path.stat().st_mtime_ns, original_read(path)) for path in (reference, candidate)]
    monkeypatch.setattr(Path, "read_bytes", lambda *_a: pytest.fail("whole-file byte allocation"))
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: pytest.fail("external process"))
    report = compare(reference, candidate, max_rms_error=0)
    assert report.valid and report.samples_identical and report.rms_difference == 0
    assert report.frames_reference == 10000 and report.compared_samples == 20000
    assert report.reference_full_scale_samples == 20000
    assert [
        (path.stat().st_mtime_ns, original_read(path)) for path in (reference, candidate)
    ] == before


@pytest.mark.parametrize(
    "kind", ["rate", "channels", "width", "duration", "empty", "truncated", "invalid", "missing"]
)
def test_invalid_or_unaligned_audio_never_passes(tmp_path, kind):
    reference = wav(tmp_path / "ref.wav", [0, 0])
    candidate = wav(tmp_path / "candidate.wav", [0, 0])
    if kind == "rate":
        wav(candidate, [0, 0], rate=16000)
    elif kind == "channels":
        wav(candidate, [0, 0], channels=2)
    elif kind == "width":
        wav(candidate, [0, 0], width=3)
    elif kind == "duration":
        wav(candidate, [0])
    elif kind == "empty":
        wav(candidate, [])
    elif kind == "truncated":
        candidate.write_bytes(candidate.read_bytes()[:-1])
    elif kind == "invalid":
        candidate.write_bytes(b"not wave")
    else:
        candidate.unlink()
    report = compare(reference, candidate)
    assert not report.valid and report.diagnostics and report.samples_identical is None


@pytest.mark.parametrize("limit", [-1, math.inf, math.nan])
def test_invalid_tolerances_are_not_silently_accepted(tmp_path, limit):
    reference = wav(tmp_path / "ref.wav", [0])
    with pytest.raises((Suno2FLPError, ValueError)):
        compare(reference, reference, max_rms_error=limit)


def test_cli_measurement_and_threshold_failure_preserve_report(tmp_path):
    reference = wav(tmp_path / "ref.wav", [0, 0])
    candidate = wav(tmp_path / "candidate.wav", [16384, -16384])
    report = tmp_path / "result.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "compare-renders",
            str(reference),
            str(candidate),
            "--max-rms-error",
            "0.1",
            "--output",
            str(report),
        ],
    )
    assert result.exit_code == 1, result.output
    data = json.loads(report.read_text(encoding="utf-8"))
    assert not data["valid"] and data["within_tolerance"] is False
    original = report.read_bytes()
    assert (
        runner.invoke(
            app, ["compare-renders", str(reference), str(candidate), "--output", str(report)]
        ).exit_code
        == 1
    )
    assert report.read_bytes() == original


@pytest.mark.parametrize("channels,extra", [(1, 1), (2, 2)])
@pytest.mark.parametrize("complete_payload", [False, True])
def test_declared_partial_samples_or_multichannel_frames_never_pass(
    tmp_path, channels, extra, complete_payload
):
    reference = wav(tmp_path / "ref.wav", [0] * (2 * channels), channels=channels)
    candidate = wav(tmp_path / "candidate.wav", [0] * (2 * channels), channels=channels)
    raw = bytearray(candidate.read_bytes())
    struct.pack_into("<I", raw, 40, 4 * channels + extra)
    if complete_payload:
        raw.extend(b"\0" * extra)
        struct.pack_into("<I", raw, 4, len(raw) - 8)
    candidate.write_bytes(raw)
    result = compare(reference, candidate, max_rms_error=0)
    assert not result.valid, "A floored frame count hid incomplete PCM data"
    assert result.samples_identical is None and result.within_tolerance is None
    assert result.diagnostics


@pytest.mark.parametrize("padded", [False, True])
def test_complete_odd_pcm8_terminal_data_remains_supported(tmp_path, padded):
    reference = wav(tmp_path / "ref.wav", [0], width=1)
    candidate = wav(tmp_path / "candidate.wav", [0], width=1)
    if padded:
        raw = bytearray(candidate.read_bytes() + b"\0")
        struct.pack_into("<I", raw, 4, len(raw) - 8)
        candidate.write_bytes(raw)
    result = compare(reference, candidate, max_rms_error=0)
    assert result.valid and result.samples_identical and result.within_tolerance


@pytest.mark.parametrize("kind", ["bits", "block_align", "riff_extent", "second_data", "tail"])
def test_inconsistent_or_ambiguous_riff_layout_never_passes(tmp_path, kind):
    reference = wav(tmp_path / "ref.wav", [0, 0])
    candidate = wav(tmp_path / "candidate.wav", [0, 0])
    raw = bytearray(candidate.read_bytes())
    if kind == "bits":
        struct.pack_into("<H", raw, 34, 15)
    elif kind == "block_align":
        struct.pack_into("<H", raw, 32, 1)
    elif kind == "riff_extent":
        struct.pack_into("<I", raw, 4, len(raw) - 9)
    else:
        raw.extend(b"data\0\0\0\0" if kind == "second_data" else b"cut")
        struct.pack_into("<I", raw, 4, len(raw) - 8)
    candidate.write_bytes(raw)
    result = compare(reference, candidate, max_rms_error=0)
    assert not result.valid and result.samples_identical is None


def test_valid_padded_ancillary_chunk_does_not_change_pcm_measurements(tmp_path):
    reference = wav(tmp_path / "ref.wav", [0, 0])
    candidate = wav(tmp_path / "candidate.wav", [0, 0])
    raw = bytearray(candidate.read_bytes() + b"JUNK\x01\0\0\0x\0")
    struct.pack_into("<I", raw, 4, len(raw) - 8)
    candidate.write_bytes(raw)
    result = compare(reference, candidate, max_rms_error=0)
    assert result.valid and result.samples_identical and result.within_tolerance
