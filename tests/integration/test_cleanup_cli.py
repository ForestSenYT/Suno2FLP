import json
from pathlib import Path

from typer.testing import CliRunner

from suno2flp.cli import app

runner = CliRunner()


def test_cleanup_cli_opt_in_output_and_source_safety(media: Path, tmp_path: Path):
    source = media / "Piano.MID"
    before = source.read_bytes()
    result = runner.invoke(app, ["clean-midi", str(source)])
    assert result.exit_code == 0, result.output
    original = json.loads(result.stdout)
    assert original["cleanup"]["changes"] == []
    result = runner.invoke(app, ["clean-midi", str(source), "--min-duration-ticks", "481"])
    assert result.exit_code == 0, result.output
    cleaned = json.loads(result.stdout)
    assert cleaned["tracks"][0]["notes"] == []
    assert cleaned["tracks"][0]["events"] == original["tracks"][0]["events"]
    assert cleaned["cleanup"]["changes"][0]["before"]["original_duration_ticks"] == 480
    output = tmp_path / "cleanup.json"
    args = ["clean-midi", str(source), "--quantize-grid-ticks", "120", "--output", str(output)]
    assert runner.invoke(app, args).exit_code == 0
    saved = output.read_bytes()
    assert runner.invoke(app, args).exit_code == 1
    assert output.read_bytes() == saved
    assert runner.invoke(app, ["clean-midi", str(source), "--output", str(source)]).exit_code == 1
    assert source.read_bytes() == before


def test_cleanup_cli_config_and_explicit_overrides(media: Path, tmp_path: Path):
    config = tmp_path / "project.yaml"
    config.write_text(
        "name: song\nmidi:\n  min_duration_ticks: 481\n"
        "  quantize: true\n  quantize_grid_ticks: 120\n"
    )
    args = ["clean-midi", str(media / "Piano.MID"), "--config", str(config)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["tracks"][0]["notes"] == []
    result = runner.invoke(app, [*args, "--min-duration-ticks", "0", "--no-quantize"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert len(data["tracks"][0]["notes"]) == 1
    assert data["cleanup"]["options"]["quantize"] is False


def test_cleanup_cli_invalid_arguments_and_sources_fail_cleanly(media: Path, tmp_path: Path):
    for flags in (
        ["--min-duration-ticks", "-1"],
        ["--quantize-grid-ticks", "0"],
        ["--quantize-grid-ticks", "120", "--no-quantize"],
    ):
        result = runner.invoke(app, ["clean-midi", str(media / "Piano.MID"), *flags])
        assert result.exit_code != 0
        assert "Error" in result.output
    result = runner.invoke(app, ["clean-midi", str(tmp_path / "missing.mid")])
    assert result.exit_code == 1
    assert "Error" in result.output
