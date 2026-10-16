"""Use authored record files only; never an external host/backend."""

import json

import pytest
from manual_record_fixtures import make_record_set
from typer.testing import CliRunner

from suno2flp.cli import app


@pytest.fixture
def record_set(tmp_path):
    return make_record_set(tmp_path)


def test_pending_cli_outputs_json_and_keeps_sources_unchanged(record_set):
    root, manifest, _, _ = record_set
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    result = CliRunner().invoke(app, ["check-host-records", str(manifest), "--root", str(root)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["integrity_valid"] and report["host_status"] == "pending_not_performed"
    assert report["stage_counts"] == {"pending_not_performed": 54}
    assert report["execution_allowed"] is False
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_cli_writes_only_exclusive_new_summary(record_set):
    root, manifest, _, _ = record_set
    destination = root / "summary.md"
    args = [
        "check-host-records",
        str(manifest),
        "--root",
        str(root),
        "--markdown",
        "--output",
        str(destination),
    ]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    text = destination.read_text(encoding="utf-8")
    assert "54" in text and "pending_not_performed" in text and "blocked" in text
    assert "explicit-odd" in text
    again = runner.invoke(app, args)
    assert again.exit_code == 1 and destination.read_text(encoding="utf-8") == text
    rejected = runner.invoke(app, args[:-1] + [str(root / "must-not-write.flp")])
    assert rejected.exit_code == 1 and not (root / "must-not-write.flp").exists()


def test_corrupt_cli_can_save_diagnostic_report_without_repairing(record_set):
    root, manifest, data, _ = record_set
    changed = root / data["records"][0]["candidate"]["path"]
    changed.write_bytes(b"corruption")
    report_path = root / "invalid.json"
    result = CliRunner().invoke(
        app,
        ["check-host-records", str(manifest), "--root", str(root), "--output", str(report_path)],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert not report["integrity_valid"] and report["writer_eligibility"] == "blocked"
    assert changed.read_bytes() == b"corruption"


def test_report_cannot_replace_a_missing_input_record(record_set):
    root, manifest, data, _ = record_set
    missing = root / data["records"][0]["record"]["path"]
    missing.unlink()
    result = CliRunner().invoke(
        app, ["check-host-records", str(manifest), "--root", str(root), "--output", str(missing)]
    )
    assert result.exit_code == 1
    assert not missing.exists()
