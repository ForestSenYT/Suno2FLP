import json
from pathlib import Path

from typer.testing import CliRunner

from suno2flp.cli import app

runner = CliRunner()


def test_help_and_doctor():
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Python" in result.stdout
    assert "unverified" in result.stdout


def test_workspace_cli_lifecycle(tmp_path: Path, media: Path):
    result = runner.invoke(app, ["init-project", "song", "--directory", str(tmp_path)])
    assert result.exit_code == 0, result.output
    project = tmp_path / "song"
    empty = runner.invoke(app, ["validate", str(project)])
    assert empty.exit_code != 0
    for path in media.iterdir():
        (project / "input" / path.name).write_bytes(path.read_bytes())
    assert runner.invoke(app, ["validate", str(project)]).exit_code == 0
    output = tmp_path / "manifest.json"
    result = runner.invoke(app, ["inspect", str(project / "input"), "--manifest", str(output)])
    assert result.exit_code == 0, result.output
    assert len(json.loads(output.read_text())["assets"]) == 2
    assert runner.invoke(app, ["inspect", str(media), "--manifest", str(output)]).exit_code != 0
    (project / "project.yaml").write_text("name: song\nnon_destructive: false\n")
    assert runner.invoke(app, ["validate", str(project)]).exit_code != 0


def test_inspect_json_and_missing_directory(media: Path, tmp_path: Path):
    result = runner.invoke(app, ["inspect", str(media)])
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)["assets"]) == 2
    assert runner.invoke(app, ["inspect", str(tmp_path / "missing")]).exit_code != 0


def test_inspect_cannot_overwrite_input(media: Path):
    source = media / "Piano.MID"
    before = source.read_bytes()
    assert runner.invoke(app, ["inspect", str(media), "--manifest", str(source)]).exit_code != 0
    assert source.read_bytes() == before
