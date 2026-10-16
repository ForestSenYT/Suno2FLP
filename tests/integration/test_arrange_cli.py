import json
from pathlib import Path

import mido
from typer.testing import CliRunner

from suno2flp.cli import app

runner = CliRunner()


def test_arrange_cli_midi_json_cleanup_and_output_safety(media: Path, tmp_path: Path):
    source = media / "Piano.MID"
    before = source.read_bytes()
    imported = runner.invoke(app, ["import-midi", str(source)])
    json_source = tmp_path / "imported.json"
    json_source.write_text(imported.stdout)
    output = tmp_path / "arrangement.json"
    args = [
        "arrange",
        str(source),
        str(json_source),
        "--target-ppq",
        "960",
        "--title",
        "Faithful test",
        "--output",
        str(output),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    assert data["metadata"]["title"] == "Faithful test"
    assert len(data["tracks"]) == 2 and data["ticks_per_beat"] == 960
    assert data["tracks"][0]["notes"][0]["duration_ticks"] == 960
    saved = output.read_bytes()
    assert runner.invoke(app, args).exit_code == 1
    assert output.read_bytes() == saved and source.read_bytes() == before
    cleaned = runner.invoke(app, ["clean-midi", str(source), "--min-duration-ticks", "481"])
    cleaned_source = tmp_path / "cleaned.json"
    cleaned_source.write_text(cleaned.stdout)
    assert runner.invoke(app, ["arrange", str(cleaned_source)]).exit_code == 1
    result = runner.invoke(app, ["arrange", str(cleaned_source), "--note-view", "active"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["tracks"][0]["notes"] == []
    assert runner.invoke(app, ["arrange", str(source), "--output", str(source)]).exit_code == 1


def test_arrange_cli_invalid_json_and_options_are_clean_errors(media: Path, tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    for args in (
        [str(bad)],
        [str(media / "Piano.MID"), "--target-ppq", "0"],
        [str(media / "Piano.MID"), "--note-view", "unknown"],
    ):
        result = runner.invoke(app, ["arrange", *args])
        assert result.exit_code != 0 and "Error" in result.output


def test_arrange_cli_conflict_fails_before_writing_and_override_is_visible(media, tmp_path):
    first = media / "Piano.MID"
    second = tmp_path / "other.mid"
    midi = mido.MidiFile(first)
    midi.tracks[0].insert(0, mido.MetaMessage("set_tempo", tempo=600000))
    midi.save(second)
    output = tmp_path / "arranged.json"
    args = ["arrange", str(first), str(second), "--output", str(output)]
    result = runner.invoke(app, args)
    assert result.exit_code == 1 and "maps disagree" in result.output
    assert not output.exists()
    result = runner.invoke(app, [*args, "--timing-source", "1"])
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text())
    assert data["tempo_map"][0]["microseconds_per_beat"] == 600000
    assert any(d["code"] == "timing_conflict_overridden" for d in data["diagnostics"])
