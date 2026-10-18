"""Thin MIDI bundle commands, explicit candidate status and prerequisite failure."""

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from suno2flp.cli import app


def test_moe_midi_commands_are_available_without_model_runtime():
    for name in ["export-yourmt3-moe-midi", "verify-yourmt3-moe-midi"]:
        result = CliRunner().invoke(app, [name, "--help"])
        assert result.exit_code == 0, result.output


def test_missing_moe_producer_is_explicit_and_creates_no_output(tmp_path):
    output = tmp_path / "new bundle"
    result = CliRunner().invoke(
        app, ["export-yourmt3-moe-midi", str(tmp_path / "missing.json"), "--output", str(output)]
    )
    assert result.exit_code == 1
    assert "Error:" in result.output and not output.exists()


def test_commands_forward_paths_and_keep_blockers(monkeypatch, tmp_path):
    import suno2flp.cli_moe_midi as cli

    calls = []
    record = SimpleNamespace(
        root=tmp_path,
        files=[],
        score=SimpleNamespace(
            status="unqualified_candidate",
            parts=[],
            clock_basis="technical-audio-seconds-not-musical-tempo",
            blockers=["unqualified"],
        ),
    )

    def export(report, output):
        calls.append((report, output))
        return record

    monkeypatch.setattr(cli, "export_moe_midi", export)
    monkeypatch.setattr(cli, "verify_moe_midi_export", lambda path: record)
    result = CliRunner().invoke(app, ["export-yourmt3-moe-midi", "source.json", "--output", "new"])
    assert result.exit_code == 0, result.output
    assert calls == [(Path("source.json"), Path("new"))]
    data = json.loads(result.output)
    assert data["status"] == "unqualified_candidate"
    assert data["writer_eligibility"] == "blocked" and data["execution_allowed"] is False
    assert data["blockers"] == ["unqualified"]
    result = CliRunner().invoke(app, ["verify-yourmt3-moe-midi", "moe-midi.json"])
    assert result.exit_code == 0 and json.loads(result.output) == data
