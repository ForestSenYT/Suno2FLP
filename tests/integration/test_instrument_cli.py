import json
from pathlib import Path

from typer.testing import CliRunner

from suno2flp.cli import app

runner = CliRunner()


def test_map_instruments_cli_and_arrange_flag_are_explicit_and_safe(media: Path, tmp_path: Path):
    midi = media / "Piano.MID"
    original = midi.read_bytes()
    arrangement = tmp_path / "arrangement.json"
    assert runner.invoke(app, ["arrange", str(midi), "--output", str(arrangement)]).exit_code == 0
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(
        "roles:\n  piano:\n    general_midi_program: 1\n    plugin_hint: example label\n"
        "mappings:\n  - source_input: 0\n    source_track_position: 0\n    role: piano\n"
    )
    output = tmp_path / "mapped.json"
    args = ["map-instruments", str(arrangement), "--mapping", str(mapping), "--output", str(output)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    assert data["tracks"][0]["instrument_roles"][0]["source_channel"] == 0
    assert data["tracks"][0]["instrument_roles"][0]["plugin_status"] == "unverified"
    saved, source = output.read_bytes(), arrangement.read_bytes()
    assert runner.invoke(app, args).exit_code == 1
    assert output.read_bytes() == saved and arrangement.read_bytes() == source
    assert (
        runner.invoke(
            app,
            [
                "map-instruments",
                str(arrangement),
                "--mapping",
                str(mapping),
                "--output",
                str(arrangement),
            ],
        ).exit_code
        == 1
    )
    result = runner.invoke(app, ["arrange", str(midi), "--instruments", str(mapping)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == data
    assert midi.read_bytes() == original


def test_bad_mapping_or_input_cli_never_creates_output(media: Path, tmp_path: Path):
    mapping = tmp_path / "bad.yaml"
    mapping.write_text("roles: {}\nmappings:\n  - role: unknown\n")
    output = tmp_path / "must-not-exist.json"
    result = runner.invoke(
        app,
        [
            "arrange",
            str(media / "Piano.MID"),
            "--instruments",
            str(mapping),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1 and "Error" in result.output
    assert not output.exists()
    result = runner.invoke(
        app,
        [
            "map-instruments",
            str(tmp_path / "missing.json"),
            "--mapping",
            str(mapping),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1 and "Error" in result.output
    assert not output.exists()
