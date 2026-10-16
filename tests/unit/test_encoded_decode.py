"""Real source inventory and missing-runtime stops retain exclusive attempt evidence."""

import json

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input


def source(tmp_path):
    path = tmp_path / "原创 sixteen.flac"
    # Original sixteen zero PCM16 samples, with independent complete frame CRC/PCM MD5.
    path.write_bytes(
        bytes.fromhex(
            "664c6143800000220010001000000000000001f400f000000010"
            "70bc8f4b72a86921468bf8e8441dce51fff86008000f96000000ae85"
        )
    )
    return path


def api():
    from suno2flp.pipeline import encoded_decode

    return encoded_decode


def test_missing_runtime_keeps_source_request_and_failure_without_a_completed_pcm(tmp_path):
    path = source(tmp_path)
    before = capture_stream_input(path)
    root = tmp_path / "new"
    with pytest.raises(OfflineError) as error:
        api().decode_encoded_audio(path, root, None)
    assert error.value.code == "audio_backend_unavailable" and error.value.blocked
    request = json.loads((root / "attempt.json").read_bytes())
    failure = json.loads((root / "failure.json").read_bytes())
    assert request["source"] == before.model_dump(mode="json")
    assert request["decoder_directory"] is None
    assert request["resampling"] == "none" and request["frame_zero_presentation_frame"] == 0
    assert request["adapters"] and request["app_python"]["sha256"]
    assert failure["error_code"] == "audio_backend_unavailable"
    assert not (root / "decoded.wav").exists() and not (root / "decode.json").exists()
    assert capture_stream_input(path) == before


def test_cancel_before_work_and_existing_output_never_replace_any_file(tmp_path):
    path = source(tmp_path)
    root = tmp_path / "new"
    with pytest.raises(OfflineError) as error:
        api().decode_encoded_audio(path, root, None, should_cancel=lambda: True)
    assert error.value.code == "user_cancelled" and not root.exists()
    root.mkdir()
    keep = root / "keep.txt"
    keep.write_bytes(b"keep")
    with pytest.raises((OfflineError, OSError)):
        api().decode_encoded_audio(path, root, None)
    assert keep.read_bytes() == b"keep" and sorted(p.name for p in root.iterdir()) == ["keep.txt"]


def test_compressed_job_finishes_real_inventory_then_records_explicit_runtime_prerequisite(
    tmp_path,
):
    from suno2flp.pipeline.audio_jobs import create_audio_job, run_audio_job, verify_audio_job

    path = source(tmp_path)
    before = capture_stream_input(path)
    created = create_audio_job(path, tmp_path / "job", "flac-v1")
    decoder = tmp_path / "missing-runtime"
    result = run_audio_job(created.record.path, decoder_directory=decoder)
    assert (
        result.job.status == "blocked"
        and result.job.history[-1].code == "audio_backend_unavailable"
    )
    assert result.job.stages[0].status == "succeeded" and result.job.stages[1].status == "blocked"
    assert result.job.stages[1].outputs == []
    inventory = json.loads(result.job.stages[0].outputs[0].path.read_bytes())
    assert inventory["codec"] == "FLAC" and inventory["frames"] == 16
    request = next(result.job.output_directory.glob("decode-*/attempt.json"))
    assert json.loads(request.read_bytes())["decoder_directory"] == str(decoder)
    assert verify_audio_job(result.record.path) == result
    assert capture_stream_input(path) == before


def test_blocked_retry_preserves_attempt_files_and_changed_requested_runtime(tmp_path):
    from suno2flp.pipeline.audio_jobs import create_audio_job, run_audio_job

    path = source(tmp_path)
    created = create_audio_job(path, tmp_path / "job", "flac-v1")
    first = run_audio_job(created.record.path, decoder_directory=tmp_path / "missing-one")
    evidence = [capture_stream_input(p) for p in first.job.output_directory.glob("decode-*/*.json")]
    assert len(evidence) == 2
    second = run_audio_job(first.record.path, decoder_directory=tmp_path / "missing-two")
    assert second.job.history[: len(first.job.history)] == first.job.history
    assert len(list(second.job.output_directory.glob("decode-*"))) == 2
    assert all(capture_stream_input(p.path) == p for p in evidence)
    assert second.job.status == "blocked" and second.job.stages[1].outputs == []


def test_empty_decode_report_does_not_attest_native_execution(tmp_path):
    from suno2flp.validator.encoded_decode import verify_encoded_decode

    report = tmp_path / "decode.json"
    report.write_text("{}")
    with pytest.raises((OfflineError, ValueError)):
        verify_encoded_decode(report)
    assert report.read_text() == "{}"


def test_cli_compressed_prerequisite_and_no_implicit_decoder_provision(tmp_path):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    path = source(tmp_path)
    runner = CliRunner()
    first = runner.invoke(
        app,
        ["create-audio-job", str(path), "--output", str(tmp_path / "job"), "--job-id", "cli-v1"],
    )
    assert first.exit_code == 0, first.output
    run = runner.invoke(
        app,
        [
            "run-audio-job",
            json.loads(first.stdout)["record"]["path"],
            "--decoder-directory",
            str(tmp_path / "missing"),
        ],
    )
    assert run.exit_code == 3, run.output
    result = json.loads(run.stdout)
    assert result["job"]["stages"][0]["status"] == "succeeded"
    assert result["job"]["history"][-1]["code"] == "audio_backend_unavailable"
    assert not (tmp_path / "missing").exists()
    check = runner.invoke(app, ["verify-audio-decoder", str(tmp_path / "missing")])
    assert check.exit_code == 3 and "audio_backend_unavailable" in check.output


def test_existing_candidate_directory_is_never_annotated_by_job_failure(tmp_path):
    from suno2flp.pipeline.audio_jobs import create_audio_job, run_audio_job

    path = source(tmp_path)
    first = create_audio_job(path, tmp_path / "job", "occupied-v1")
    root = first.job.output_directory / "decode-00000003"
    root.mkdir()
    (root / "keep").write_bytes(b"unchanged")
    result = run_audio_job(first.record.path)
    assert result.job.status == "failed"
    assert sorted(p.name for p in root.iterdir()) == ["keep"]
