"""CLI and future GUI share the actual persistent application service."""

import json
import wave

from typer.testing import CliRunner

from suno2flp.cli import app


def test_cli_create_run_verify_and_cancel_are_explicit(tmp_path):
    path = tmp_path / "song.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "none"))
        stream.writeframes(b"\0" * 8)
    runner = CliRunner()
    created = runner.invoke(
        app,
        ["create-audio-job", str(path), "--output", str(tmp_path / "job"), "--job-id", "song-v1"],
    )
    assert created.exit_code == 0, created.output
    first = json.loads(created.stdout)
    assert first["job"]["status"] == "queued"
    run = runner.invoke(app, ["run-audio-job", first["record"]["path"]])
    assert run.exit_code == 3, run.output
    result = json.loads(run.stdout)
    assert result["job"]["status"] == "blocked"
    verify = runner.invoke(app, ["verify-audio-job", result["record"]["path"]])
    assert verify.exit_code == 0, verify.output
    another = runner.invoke(
        app,
        [
            "create-audio-job",
            str(path),
            "--output",
            str(tmp_path / "cancel"),
            "--job-id",
            "cancel-v1",
        ],
    )
    first = json.loads(another.stdout)
    path.unlink()
    cancelled = runner.invoke(app, ["cancel-audio-job", first["record"]["path"]])
    assert cancelled.exit_code == 0, cancelled.output
    assert json.loads(cancelled.stdout)["job"]["status"] == "cancelled"


def test_corrupt_audio_run_exits_one_with_persisted_failure(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"bad")
    runner = CliRunner()
    first = runner.invoke(
        app,
        ["create-audio-job", str(path), "--output", str(tmp_path / "job"), "--job-id", "bad-v1"],
    )
    assert first.exit_code == 0, first.output
    run = runner.invoke(app, ["run-audio-job", json.loads(first.stdout)["record"]["path"]])
    assert run.exit_code == 1, run.output
    assert json.loads(run.stdout)["job"]["status"] == "failed"
