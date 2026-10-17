"""Thin complete-candidate commands with synthetic native boundaries, never music proof."""

import json

import pytest
from test_separation_pipeline import protocol as protocol
from test_spleeter_backend import recipe as recipe
from typer.testing import CliRunner

from suno2flp.cli import app


@pytest.mark.parametrize(
    "command,option", [("separate-audio", "--output"), ("verify-separation", "--replay-output")]
)
def test_complete_candidate_commands_have_explicit_prerequisite_failures(tmp_path, command, option):
    missing, output = tmp_path / "missing.json", tmp_path / "new"
    arguments = [command, str(missing)]
    if command == "separate-audio":
        arguments.append(str(tmp_path / "backend"))
    result = CliRunner().invoke(app, [*arguments, option, str(output)])
    assert result.exit_code == 1 and "Error:" in result.output
    assert not output.exists()


def test_commands_keep_synthetic_candidate_and_replay_unqualified(protocol, tmp_path):
    candidate, replay = tmp_path / "candidate", tmp_path / "replay"
    result = CliRunner().invoke(
        app,
        ["separate-audio", str(protocol.decode), str(protocol.backend), "--output", str(candidate)],
    )
    assert result.exit_code == 0, result.output
    status = json.loads(result.stdout)
    assert status["status"] == "inferred_candidate" and status["frames"] == 37
    assert status["model_qualification"] == "not_assessed"
    assert status["writer_eligibility"] == "blocked" and not status["execution_allowed"]
    result = CliRunner().invoke(
        app,
        ["verify-separation", str(candidate / "separation.json"), "--replay-output", str(replay)],
    )
    assert result.exit_code == 0, result.output
    status = json.loads(result.stdout)
    assert status["status"] == "complete_native_replay_matched"
    assert status["musical_correctness"] == "not_proven_per_song"
    assert (replay / "replay.json").is_file()
