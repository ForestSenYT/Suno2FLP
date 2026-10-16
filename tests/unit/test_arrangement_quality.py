import json

import pytest
from offline_fixtures import arrangement_file
from typer.testing import CliRunner

from suno2flp.cli import app
from suno2flp.core.models import ArrangementOptions, MidiCleanupOptions
from suno2flp.midi_processor import DeterministicMidiProcessor


def verify(path):
    from suno2flp.validator.arrangement import verify_arrangement_file

    return verify_arrangement_file(path)


def test_current_original_replay_is_read_only_and_exact(tmp_path, monkeypatch):
    path, arrangement, original = arrangement_file(
        tmp_path, options=ArrangementOptions(target_ppq=960)
    )
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: pytest.fail("process invoked"))
    result = verify(path)
    assert result.valid and result.source_count == 1 and result.note_count == 1
    assert result.track_count == 2 and result.event_count == 7
    assert result.arrangement_fingerprint == result.reference_fingerprint
    assert result.host_compatibility == "unverified" and result.writer_eligibility == "blocked"
    assert not result.execution_allowed
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}


@pytest.mark.parametrize(
    "field,value",
    [
        ("start_tick", 241),
        ("duration_ticks", 481),
        ("channel", 1),
        ("pitch", 61),
        ("velocity", 80),
        ("original_start_tick", 119),
        ("note_on_event_index", 0),
    ],
)
def test_arranged_note_changes_fail_current_source_replay(tmp_path, field, value):
    path, arrangement, _ = arrangement_file(tmp_path)
    setattr(arrangement.tracks[1].notes[0], field, value)
    path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    result = verify(path)
    assert not result.valid and any(
        d.code == "arrangement_replay_mismatch" for d in result.diagnostics
    )


@pytest.mark.parametrize(
    "change", ["tempo", "meter", "event", "source_hash", "track", "index", "role"]
)
def test_map_event_identity_and_role_forgery_are_detected(tmp_path, change):
    path, arrangement, _ = arrangement_file(tmp_path)
    if change == "tempo":
        arrangement.tempo_map[0].microseconds_per_beat = 600000
    elif change == "meter":
        arrangement.meter_map[0].numerator = 3
    elif change == "event":
        arrangement.sources[0].midi.tracks[1].events[1].delta_ticks = 999
    elif change == "source_hash":
        arrangement.sources[0].midi.source_sha256 = "0" * 64
    elif change == "track":
        arrangement.tracks.reverse()
    elif change == "index":
        arrangement.sources[0].input_index = 2
    else:
        arrangement.tracks[1].instrument_hint = "Unrecorded change"
    path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    assert not verify(path).valid


def test_cleanup_is_replayed_from_original_instead_of_trusting_changed_snapshot(tmp_path):
    from suno2flp.arrangement import FaithfulArrangementEngine
    from suno2flp.core.models import MusicalMetadata

    path, _, original = arrangement_file(tmp_path)
    cleaned = DeterministicMidiProcessor().clean(
        original, MidiCleanupOptions(min_duration_ticks=300)
    )
    arrangement = FaithfulArrangementEngine().arrange(
        [cleaned],
        MusicalMetadata(),
        options=ArrangementOptions(note_view="active"),
    )
    path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    assert verify(path).valid and verify(path).note_count == 0
    arrangement.sources[0].midi.cleanup.changes.clear()
    path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    assert not verify(path).valid


@pytest.mark.parametrize(
    "change", ["missing", "changed", "bad_json", "no_provenance", "duplicate_json"]
)
def test_missing_stale_and_unverifiable_inputs_never_pass(tmp_path, change):
    path, arrangement, original = arrangement_file(tmp_path)
    if change == "missing":
        original.source.unlink()
    elif change == "changed":
        original.source.write_bytes(b"corrupted")
    elif change == "bad_json":
        path.write_text("{", encoding="utf-8")
    elif change == "no_provenance":
        arrangement.sources.clear()
        path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    else:
        path.write_text('{"mode":"faithful","mode":"faithful"}', encoding="utf-8")
    result = verify(path)
    assert not result.valid and result.diagnostics


def test_quality_cli_reports_and_refuses_overwrite(tmp_path):
    path, _, _ = arrangement_file(tmp_path)
    destination = tmp_path / "quality.json"
    runner = CliRunner()
    result = runner.invoke(app, ["verify-arrangement", str(path), "--output", str(destination)])
    assert result.exit_code == 0, result.output
    report = json.loads(destination.read_text(encoding="utf-8"))
    assert report["valid"] and report["host_compatibility"] == "unverified"
    before = destination.read_bytes()
    assert (
        runner.invoke(
            app, ["verify-arrangement", str(path), "--output", str(destination)]
        ).exit_code
        == 1
    )
    assert destination.read_bytes() == before


@pytest.mark.parametrize("destination_name", ["later.mid", "roles.json"])
def test_early_missing_source_still_protects_all_declared_inputs(tmp_path, destination_name):
    from offline_fixtures import write_midi

    from suno2flp.arrangement import ExplicitInstrumentMapper, FaithfulArrangementEngine
    from suno2flp.core.instrument_config import load_instrument_mapping

    path, arrangement, original = arrangement_file(tmp_path)
    later = write_midi(tmp_path / "later.mid")
    roles = tmp_path / "roles.json"
    roles.write_text('{"roles": {}, "mappings": []}', encoding="utf-8")
    arrangement = FaithfulArrangementEngine().arrange([original, later], arrangement.metadata)
    arrangement = ExplicitInstrumentMapper().apply(arrangement, load_instrument_mapping(roles))
    path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    assert verify(path).valid
    original.source.unlink()
    later.source.unlink()
    roles.unlink()

    destination = tmp_path / destination_name
    result = CliRunner().invoke(
        app, ["verify-arrangement", str(path), "--output", str(destination)]
    )
    assert result.exit_code == 1, result.output
    assert not destination.exists(), "A failure report occupied a declared missing input"
    assert set(verify(path).referenced_paths) == {path, original.source, later.source, roles}
