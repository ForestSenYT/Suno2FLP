import json
import struct
from pathlib import Path

import mido
from typer.testing import CliRunner

from suno2flp.cli import app

runner = CliRunner()


def test_import_midi_cli_prints_details_and_exclusively_writes_output(media: Path, tmp_path: Path):
    source = media / "Piano.MID"
    before = source.read_bytes()
    result = runner.invoke(app, ["import-midi", str(source)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["tracks"][0]["notes"][0]["original_duration_ticks"] == 480
    output = tmp_path / "import.json"
    result = runner.invoke(app, ["import-midi", str(source), "--output", str(output)])
    assert result.exit_code == 0, result.output
    saved = output.read_bytes()
    assert runner.invoke(app, ["import-midi", str(source), "--output", str(output)]).exit_code == 1
    assert output.read_bytes() == saved
    assert runner.invoke(app, ["import-midi", str(source), "--output", str(source)]).exit_code == 1
    assert source.read_bytes() == before
    assert runner.invoke(app, ["import-midi", str(tmp_path / "missing.mid")]).exit_code == 1


def test_import_midi_cli_diagnostic_errors_and_warnings(tmp_path: Path):
    source = tmp_path / "invalid.mid"
    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=0)]))
    midi.save(source)
    result = runner.invoke(app, ["import-midi", str(source)])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["diagnostics"][0]["code"] == "invalid_tempo"
    output = tmp_path / "partial.json"
    assert runner.invoke(app, ["import-midi", str(source), "--output", str(output)]).exit_code == 1
    assert json.loads(output.read_text())["tracks"][0]["events"]
    midi.tracks[0] = mido.MidiTrack([mido.Message("note_on", note=60)])
    midi.save(source)
    result = runner.invoke(app, ["import-midi", str(source)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["diagnostics"][0]["code"] == "unclosed_note"


def test_malformed_key_signature_cli_reports_error_without_traceback(tmp_path: Path):
    source = tmp_path / "bad-key.mid"
    events = bytes.fromhex("00ff5902080000ff2f00")
    source.write_bytes(
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, 480)
        + b"MTrk"
        + struct.pack(">I", len(events))
        + events
    )
    result = runner.invoke(app, ["import-midi", str(source)])
    assert result.exit_code == 1
    assert "Error: Cannot import MIDI" in result.output
    assert "Traceback" not in result.output
