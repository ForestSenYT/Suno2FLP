"""Discovery and explicit prerequisite failures do not load native model packages."""

from typer.testing import CliRunner

from suno2flp.cli import app


def test_stem_commands_are_discoverable_without_native_packages():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "transcribe-stems" in result.stdout and "verify-stem-transcription" in result.stdout


def test_missing_separation_cannot_create_output_or_claim_delivery(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "transcribe-stems",
            str(tmp_path / "missing/separation.json"),
            "--backend",
            str(tmp_path / "missing-backend"),
            "--output",
            str(tmp_path / "attempt"),
        ],
    )
    assert result.exit_code == 1 and "Error:" in result.output
    assert "unqualified_candidate" not in result.output
    assert not (tmp_path / "attempt").exists()
