"""Thin development commands and explicit absent prerequisites."""

from pathlib import Path

from typer.testing import CliRunner

from suno2flp.cli import app


def test_rhythm_commands_have_real_help() -> None:
    runner = CliRunner()
    for command in (
        "prepare-beat-backend",
        "probe-beat-backend",
        "analyze-beats",
        "verify-beat-analysis",
        "score-beats",
        "verify-beat-score",
    ):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, result.output


def test_missing_prerequisites_fail_without_output(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "analyze-beats",
            str(tmp_path / "absent.json"),
            "--backend",
            str(tmp_path / "absent-backend"),
            "--output",
            str(tmp_path / "result"),
        ],
    )
    assert result.exit_code == 1
    assert not (tmp_path / "result").exists()
