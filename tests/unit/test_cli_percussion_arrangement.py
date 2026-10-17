"""CLI forwards explicit inputs to the real services, without model/host actions."""

import json
from pathlib import Path

import pytest
from test_percussion_arrangement import inputs
from typer.testing import CliRunner

from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.cli import app


@pytest.mark.parametrize(
    "command", ["compose-percussion-arrangement", "verify-percussion-arrangement"]
)
def test_help_and_missing_prerequisites_are_explicit(tmp_path, command):
    runner = CliRunner()
    assert runner.invoke(app, [command, "--help"]).exit_code == 0
    arguments = [command, str(tmp_path / "missing.json")]
    if command.startswith("compose"):
        arguments += ["--drums", str(tmp_path / "drums.json"), "--output", str(tmp_path / "out")]
    result = runner.invoke(app, arguments)
    assert result.exit_code == 1 and "Error:" in result.output
    assert not (tmp_path / "out").exists()


def test_thin_forwarding_keeps_candidate_status(monkeypatch):
    import suno2flp.cli_percussion_arrangement as cli

    calls = []
    record = build_percussion_arrangement(inputs())

    def compose(batch, drums, output, **kwargs):
        calls.append((batch, drums, output, kwargs))
        return record

    def verify(report):
        calls.append(report)
        return record

    monkeypatch.setattr(cli, "compose_percussion_arrangement", compose)
    monkeypatch.setattr(cli, "verify_percussion_arrangement", verify)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "compose-percussion-arrangement",
            "batch.json",
            "--drums",
            "drums.json",
            "--beats",
            "beats.json",
            "--output",
            "new",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "unqualified_candidate" and data["drum_onsets"] == 2
    assert data["execution_allowed"] is False and data["writer_eligibility"] == "blocked"
    assert calls == [
        (Path("batch.json"), Path("drums.json"), Path("new"), {"beats_path": Path("beats.json")})
    ]
    checked = runner.invoke(app, ["verify-percussion-arrangement", "saved.json"])
    assert checked.exit_code == 0 and calls[-1] == Path("saved.json")
    assert json.loads(checked.output)["verification"] == "current-artifact-reconstruction"
