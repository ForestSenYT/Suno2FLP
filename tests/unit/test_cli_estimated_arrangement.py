"""Thin CLI delegates to the same file services and exposes all retained gates."""

import json
from pathlib import Path

from test_estimated_arrangement import inputs
from typer.testing import CliRunner

from suno2flp.arrangement.inferred import build_estimated_arrangement
from suno2flp.cli import app


def test_estimated_arrangement_commands_are_available():
    for command in ("compose-estimated-arrangement", "verify-estimated-arrangement"):
        result = CliRunner().invoke(app, [command, "--help"])
        assert result.exit_code == 0, result.output


def test_commands_delegate_and_preserve_unqualified_summary(monkeypatch):
    from suno2flp import cli_estimated_arrangement as commands

    calls = []
    record = build_estimated_arrangement(inputs())

    def compose(batch, output, *, beats_path):
        calls.append((batch, output, beats_path))
        return record

    def verify(path):
        calls.append(path)
        return record

    monkeypatch.setattr(commands, "compose_estimated_arrangement", compose)
    monkeypatch.setattr(commands, "verify_estimated_arrangement", verify)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["compose-estimated-arrangement", "batch.json", "--output", "new", "--beats", "beats.json"],
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["status"] == "unqualified_candidate" and summary["execution_allowed"] is False
    assert summary["notes"] == 6 and summary["writer_eligibility"] == "blocked"
    assert "drums-not-transcribed" in summary["blockers"]
    assert calls[0] == (Path("batch.json"), Path("new"), Path("beats.json"))
    result = runner.invoke(app, ["verify-estimated-arrangement", "report.json"])
    assert result.exit_code == 0 and calls[-1] == Path("report.json")
    assert json.loads(result.output)["verification"] == "current-artifact-reconstruction"


def test_missing_prerequisite_failure_is_explicit(monkeypatch):
    from suno2flp import cli_estimated_arrangement as commands

    def refused(*args, **kwargs):
        raise ValueError("source changed")

    monkeypatch.setattr(commands, "compose_estimated_arrangement", refused)
    result = CliRunner().invoke(
        app, ["compose-estimated-arrangement", "batch.json", "--output", "new"]
    )
    assert result.exit_code == 1 and "source changed" in result.output
    assert "unqualified_candidate" not in result.output
