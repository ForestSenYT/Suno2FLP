"""CLI orchestration uses real tiny source evidence with the explicit mocked boundary."""

import json

import pytest
from test_drum_transcription import drums as drums
from test_drum_transcription import protocol as protocol
from test_drum_transcription import recipe as recipe
from typer.testing import CliRunner

from suno2flp.cli import app


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_candidate_replay_annotation_commands_keep_gates(drums, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "transcribe-drums",
            str(drums.separation),
            "--separation-replay",
            str(drums.receipt),
            "--backend",
            str(drums.backend),
            "--output",
            str(tmp_path / "drums"),
        ],
    )
    assert result.exit_code == 0, result.output
    value = json.loads(result.stdout)
    assert value["status"] == "unqualified_candidate" and value["execution_allowed"] is False
    assert value["writer_eligibility"] == "blocked" and value["events"] == 1
    candidate = tmp_path / "drums/drum-transcription.json"
    result = runner.invoke(
        app, ["verify-drum-transcription", str(candidate), "--output", str(tmp_path / "replay")]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["complete_match"] is True
    annotation = tmp_path / "annotation.json"
    assert (
        runner.invoke(
            app, ["export-drum-annotation", str(candidate), "--output", str(annotation)]
        ).exit_code
        == 0
    )
    assert json.loads(annotation.read_bytes())["origin"] == "inferred_candidate"
    assert (
        runner.invoke(
            app, ["export-drum-annotation", str(candidate), "--output", str(annotation)]
        ).exit_code
        == 1
    )


@pytest.mark.parametrize(
    "command",
    [
        "prepare-drum-backend",
        "verify-drum-backend",
        "transcribe-drums",
        "verify-drum-transcription",
        "export-drum-annotation",
    ],
)
def test_help_has_no_native_prerequisite(command):
    assert CliRunner().invoke(app, [command, "--help"]).exit_code == 0


@pytest.mark.parametrize(
    "command", ["verify-drum-backend", "verify-drum-transcription", "export-drum-annotation"]
)
def test_missing_inputs_fail_explicitly(command, tmp_path):
    result = CliRunner().invoke(
        app, [command, str(tmp_path / "missing"), "--output", str(tmp_path / "output")]
    )
    assert result.exit_code == 1 and "Error:" in result.output
    assert not (tmp_path / "output").exists()
