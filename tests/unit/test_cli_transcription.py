"""Thin commands fail explicitly without native preparation; CLI startup stays offline."""

from typer.testing import CliRunner

from suno2flp.cli import app


def test_transcription_commands_are_discoverable_without_model_packages() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in (
        "prepare-basic-pitch",
        "verify-basic-pitch",
        "transcribe-audio",
        "verify-transcription",
    ):
        assert name in result.stdout


def test_missing_backend_reports_failure_and_never_claims_delivery(tmp_path) -> None:
    result = CliRunner().invoke(
        app,
        ["verify-basic-pitch", str(tmp_path / "missing"), "--output", str(tmp_path / "attempt")],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert not (tmp_path / "attempt").exists()
