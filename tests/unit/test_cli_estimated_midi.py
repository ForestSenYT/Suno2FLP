"""CLI forwarding and honest candidate status; producer verification is tested separately."""

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from suno2flp.cli import app


def test_export_and_verify_keep_candidate_status(monkeypatch, tmp_path):
    import suno2flp.cli_estimated_midi as cli

    calls = []
    record = SimpleNamespace(
        midi=SimpleNamespace(path=tmp_path / "candidate.mid"),
        score=SimpleNamespace(
            status="unqualified_candidate",
            parts=[],
            clock_basis="technical-120bpm-not-estimated-musical-tempo",
            blockers=["model-not-qualified"],
        ),
    )

    def export(batch, drums, output, *, beats_path=None):
        calls.append((batch, drums, output, beats_path))
        return record

    monkeypatch.setattr(cli, "export_estimated_midi", export)
    result = CliRunner().invoke(
        app,
        [
            "export-estimated-midi",
            "batch.json",
            "--drums",
            "drums.json",
            "--output",
            "new-output",
            "--beats",
            "beats.json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "unqualified_candidate" and data["execution_allowed"] is False
    assert data["writer_eligibility"] == "blocked"
    assert calls == [
        (Path("batch.json"), Path("drums.json"), Path("new-output"), Path("beats.json"))
    ]
    monkeypatch.setattr(cli, "verify_estimated_midi_export", lambda path: record)
    result = CliRunner().invoke(app, ["verify-estimated-midi", "estimated-midi.json"])
    assert result.exit_code == 0 and json.loads(result.output)["execution_allowed"] is False


def test_missing_producers_fail_without_output(tmp_path):
    output = tmp_path / "missing-output"
    result = CliRunner().invoke(
        app,
        [
            "export-estimated-midi",
            str(tmp_path / "missing.json"),
            "--drums",
            str(tmp_path / "drums.json"),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1 and not output.exists()
