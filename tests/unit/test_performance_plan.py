"""Original synthetic SMF cases for the lossless pre-encoding boundary."""

import json
from pathlib import Path

import mido
import pytest
from typer.testing import CliRunner

from suno2flp.arrangement import FaithfulArrangementEngine
from suno2flp.cli import app
from suno2flp.core.models import ArrangementOptions, MusicalMetadata
from suno2flp.importer import MidiFileImporter


def make_arrangement(tmp_path: Path, *, tempo: int = 500000, ppq: int = 480) -> Path:
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage("set_tempo", tempo=tempo),
                mido.MetaMessage("set_tempo", tempo=600000, time=ppq),
                mido.MetaMessage("end_of_track", time=ppq * 2),
            ]
        )
    )
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("program_change", channel=3, program=65),
                mido.Message("control_change", channel=3, control=64, value=127),
                mido.Message("note_on", channel=3, note=60, velocity=90, time=1),
                mido.Message("note_off", channel=3, note=60, time=ppq * 2 - 1),
                mido.Message("control_change", channel=3, control=64, value=0, time=ppq),
                mido.MetaMessage("end_of_track"),
            ]
        )
    )
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("control_change", channel=3, control=7, value=100, time=ppq * 3),
                mido.MetaMessage("end_of_track"),
            ]
        )
    )
    source = tmp_path / "source.mid"
    midi.save(source)
    arrangement = FaithfulArrangementEngine().arrange(
        [MidiFileImporter().import_file(source)], MusicalMetadata(), "faithful"
    )
    path = tmp_path / "arrangement.json"
    path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    return path


def planner():
    from suno2flp.flp_builder.performance import plan_performance_file

    return plan_performance_file


def rational(value):
    return value.numerator, value.denominator


def test_every_event_order_controls_and_elapsed_time_are_preserved(tmp_path):
    path = make_arrangement(tmp_path)
    before = path.read_bytes()
    result = planner()(path, target_ppq=960)
    assert result.source_verified and result.target_grid_exact
    assert result.execution_allowed is False and result.writer_eligibility == "blocked"
    assert result.arrangement.model_dump_json() == path.read_text("utf-8")
    assert len(result.tracks) == 3
    track = result.tracks[1]
    assert [event.source_event_index for event in track.events] == list(range(6))
    assert rational(track.events[2].position.target_tick) == (2, 1)
    assert rational(track.events[2].position.elapsed_microseconds) == (3125, 3)
    assert rational(track.events[3].position.elapsed_microseconds) == (1100000, 1)
    assert rational(track.end.elapsed_microseconds) == (1700000, 1)
    assert rational(result.notes[0].end.elapsed_microseconds) == (1100000, 1)
    assert len(result.untranslated_events) == 4  # Program + three CC, including control-only track.
    assert result.event_type_counts["control_change"] == 3
    assert result.tempo_scalar_exact
    assert [t.exact_milli_bpm for t in result.tempos] == [120000, 100000]
    assert path.read_bytes() == before


def test_target_grid_loss_is_reported_as_fraction_never_rounded(tmp_path):
    result = planner()(make_arrangement(tmp_path), target_ppq=96)
    assert not result.target_grid_exact
    assert rational(result.tracks[1].events[2].position.target_tick) == (1, 5)
    assert "performance_ppq_inexact" in {d.code for d in result.diagnostics}


def test_tempo_scalar_loss_is_quantified_without_changing_tempo(tmp_path):
    result = planner()(make_arrangement(tmp_path, tempo=434300))
    tempo = result.tempos[0]
    assert tempo.source.microseconds_per_beat == 434300
    assert rational(tempo.milli_bpm) == (600000000, 4343)
    assert tempo.exact_milli_bpm is None
    assert not result.tempo_scalar_exact
    assert "performance_tempo_scalar_inexact" in {d.code for d in result.diagnostics}


@pytest.mark.parametrize("target_ppq", [0, -1, True, 1.5, 65536])
def test_invalid_ppq_is_rejected(tmp_path, target_ppq):
    with pytest.raises(ValueError, match="PPQ"):
        planner()(make_arrangement(tmp_path), target_ppq=target_ppq)


def test_modified_arrangement_is_rejected_even_with_original_source_hash(tmp_path):
    path = make_arrangement(tmp_path)
    data = json.loads(path.read_text("utf-8"))
    next(track for track in data["tracks"] if track["notes"])["notes"][0]["velocity"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="replay"):
        planner()(path)


def test_saved_plan_reconstructs_every_field_and_current_sources(tmp_path):
    path = make_arrangement(tmp_path)
    result = planner()(path)
    from suno2flp.flp_builder.performance import verify_performance_file

    saved = tmp_path / "plan.json"
    saved.write_text(result.model_dump_json(), encoding="utf-8")
    assert verify_performance_file(saved) == result
    modified = result.model_dump(mode="json")
    modified["tracks"][1]["events"].reverse()
    saved.write_text(json.dumps(modified), encoding="utf-8")
    with pytest.raises(ValueError, match="replay"):
        verify_performance_file(saved)
    saved.write_text(result.model_dump_json(), encoding="utf-8")
    (tmp_path / "source.mid").write_bytes(b"changed source")
    with pytest.raises(ValueError, match="replay"):
        verify_performance_file(saved)


def test_cli_exclusive_plan_and_replay_without_host(tmp_path, monkeypatch):
    path = make_arrangement(tmp_path)
    output = tmp_path / "plan.json"
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("No host or backend process may be launched")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    runner = CliRunner()
    args = ["plan-midi-performance", str(path), "--target-ppq", "960", "--output", str(output)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "blocked" in result.output
    assert runner.invoke(app, ["verify-midi-performance", str(output)]).exit_code == 0
    original = output.read_bytes()
    assert runner.invoke(app, args).exit_code != 0
    assert output.read_bytes() == original
    assert not list(tmp_path.glob("*.flp"))


def save_arrangement(tmp_path, imports, options=None):
    arrangement = FaithfulArrangementEngine().arrange(
        imports, MusicalMetadata(), "faithful", options=options
    )
    path = tmp_path / "combined.json"
    path.write_text(arrangement.model_dump_json(), encoding="utf-8")
    return path


def test_equivalent_maps_at_different_ppq_keep_source_identity_and_order(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    make_arrangement(first, ppq=480)
    make_arrangement(second, ppq=960)
    imports = [MidiFileImporter().import_file(p / "source.mid") for p in (first, second)]
    result = planner()(save_arrangement(tmp_path, imports), target_ppq=960)
    assert len(result.tracks) == 6 and len(result.untranslated_events) == 8
    assert result.untranslated_events[0].source_input == 0
    assert result.untranslated_events[4].source_input == 1
    assert {e.source_channel for e in result.untranslated_events} == {3}
    assert rational(result.tracks[1].events[2].position.target_tick) == (2, 1)
    assert rational(result.tracks[4].events[2].position.target_tick) == (1, 1)
    assert rational(result.tracks[1].events[3].position.elapsed_microseconds) == (1100000, 1)
    assert rational(result.tracks[4].events[3].position.elapsed_microseconds) == (1100000, 1)
    assert result.event_type_counts["set_tempo"] == 4 and len(result.tempos) == 2


def test_explicit_timing_authority_must_not_hide_a_different_source_map(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    make_arrangement(first)
    make_arrangement(second, tempo=400000)
    imports = [MidiFileImporter().import_file(p / "source.mid") for p in (first, second)]
    path = save_arrangement(tmp_path, imports, ArrangementOptions(timing_source=0))
    with pytest.raises(ValueError, match="overridden"):
        planner()(path)


def test_no_prior_rounding_policy_even_if_notes_happen_to_fit(tmp_path):
    make_arrangement(tmp_path)
    imported = MidiFileImporter().import_file(tmp_path / "source.mid")
    path = save_arrangement(tmp_path, [imported], ArrangementOptions(ppq_rounding="nearest"))
    with pytest.raises(ValueError, match="rounding"):
        planner()(path)


def test_selected_cleanup_changes_cannot_claim_original_performance(tmp_path):
    from suno2flp.core.config import MidiPreferences
    from suno2flp.midi_processor import DeterministicMidiProcessor

    make_arrangement(tmp_path)
    imported = MidiFileImporter().import_file(tmp_path / "source.mid")
    cleaned = DeterministicMidiProcessor().clean(
        imported, MidiPreferences(quantize=True, quantize_grid_ticks=120)
    )
    path = save_arrangement(tmp_path, [cleaned], ArrangementOptions(note_view="active"))
    with pytest.raises(ValueError, match="cleanup"):
        planner()(path)
    path = save_arrangement(tmp_path, [imported], ArrangementOptions(note_view="imported"))
    assert rational(planner()(path).notes[0].start.target_tick) == (1, 1)


def test_default_tempo_and_initial_silence_zero_duration_are_not_invented_away(tmp_path):
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", note=60, time=480),
                mido.Message("note_off", note=60),
                mido.MetaMessage("end_of_track", time=480),
            ]
        )
    )
    source = tmp_path / "default.mid"
    midi.save(source)
    result = planner()(save_arrangement(tmp_path, [MidiFileImporter().import_file(source)]))
    assert result.tempos[0].source.is_default
    assert result.tempos[0].source.microseconds_per_beat == 500000
    assert rational(result.notes[0].start.elapsed_microseconds) == (500000, 1)
    assert result.notes[0].start == result.notes[0].end
    assert rational(result.tracks[0].end.elapsed_microseconds) == (1000000, 1)
    assert "performance_zero_duration" in {d.code for d in result.diagnostics}


def test_repeated_tempos_and_same_tick_controller_order_remain_in_source_snapshot(tmp_path):
    make_arrangement(tmp_path)
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(source)
    midi.tracks[0].insert(1, mido.MetaMessage("set_tempo", tempo=500000))
    midi.tracks[1].insert(2, mido.Message("control_change", channel=3, control=64, value=0))
    midi.save(source)
    result = planner()(save_arrangement(tmp_path, [MidiFileImporter().import_file(source)]))
    assert result.event_type_counts["set_tempo"] == 3 and len(result.tempos) == 2
    events = result.arrangement.sources[0].midi.tracks[1].events
    assert [event.message["value"] for event in events[1:3]] == [127, 0]
    assert result.tracks[1].events[1].position == result.tracks[1].events[2].position
    assert [e.source_event_index for e in result.untranslated_events[:3]] == [0, 1, 2]


def test_meter_change_and_unrepresentable_meter_position_are_explicit(tmp_path):
    make_arrangement(tmp_path)
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(source)
    midi.tracks[0].insert(1, mido.MetaMessage("time_signature", numerator=3, denominator=4, time=1))
    midi.save(source)
    result = planner()(
        save_arrangement(tmp_path, [MidiFileImporter().import_file(source)]), target_ppq=96
    )
    assert not result.target_grid_exact
    assert "performance_meter_encoding_unverified" in {d.code for d in result.diagnostics}


def test_integer_but_out_of_range_ticks_are_distinct_from_ppq_loss(tmp_path):
    midi = mido.MidiFile(type=0, ticks_per_beat=24)
    midi.tracks.append(mido.MidiTrack([mido.MetaMessage("end_of_track", time=2**28 - 1)]))
    source = tmp_path / "long.mid"
    midi.save(source)
    result = planner()(
        save_arrangement(tmp_path, [MidiFileImporter().import_file(source)]), target_ppq=960
    )
    assert result.target_grid_exact
    assert "performance_tick_range" in {d.code for d in result.diagnostics}


@pytest.mark.parametrize("kind", ["pitchwheel", "aftertouch", "polytouch", "sysex"])
def test_other_performance_events_are_retained_and_untranslated(tmp_path, kind):
    make_arrangement(tmp_path)
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(source)
    midi.tracks[1].insert(0, mido.Message(kind))
    midi.save(source)
    result = planner()(save_arrangement(tmp_path, [MidiFileImporter().import_file(source)]))
    assert result.event_type_counts[kind] == 1
    assert result.untranslated_events[0].event_type == kind
    assert result.arrangement.sources[0].midi.tracks[1].events[0].message["type"] == kind


@pytest.mark.parametrize("mutation", ["time", "tempo", "message", "hash", "permission"])
def test_report_mutations_never_gain_authority(tmp_path, mutation):
    result = planner()(make_arrangement(tmp_path))
    from suno2flp.flp_builder.performance import verify_performance_file

    data = result.model_dump(mode="json")
    if mutation == "time":
        data["tracks"][1]["events"][2]["position"]["elapsed_microseconds"]["numerator"] += 1
    elif mutation == "tempo":
        data["tempos"][0]["exact_milli_bpm"] = 120001
    elif mutation == "message":
        data["arrangement"]["sources"][0]["midi"]["tracks"][1]["events"][1]["message"]["value"] = 0
    elif mutation == "hash":
        data["arrangement_fingerprint"] = "0" * 64
    else:
        data["execution_allowed"] = True
    saved = tmp_path / "mutated.json"
    saved.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_performance_file(saved)


def test_duplicate_json_key_and_missing_original_never_publish_output(tmp_path):
    path = make_arrangement(tmp_path)
    result = planner()(path)
    from suno2flp.flp_builder.performance import verify_performance_file

    saved = tmp_path / "duplicate.json"
    text = result.model_dump_json()
    saved.write_text('{"target_ppq":480,' + text[1:], encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        verify_performance_file(saved)
    source = tmp_path / "source.mid"
    source.unlink()  # Only the test-owned synthetic fixture.
    invocation = CliRunner().invoke(
        app, ["plan-midi-performance", str(path), "--output", str(source)]
    )
    assert invocation.exit_code != 0 and not source.exists()


def test_plan_deterministic_with_complete_input_identity(tmp_path):
    path = make_arrangement(tmp_path)
    first = planner()(path, target_ppq=960)
    second = planner()(path, target_ppq=960)
    assert first.model_dump_json() == second.model_dump_json()
    assert {p.path for p in first.input_files} == {path, tmp_path / "source.mid"}


def test_publication_detects_source_changes_and_never_reports_success(tmp_path, monkeypatch):
    import suno2flp.cli as cli_module

    path = make_arrangement(tmp_path)
    output = tmp_path / "plan.json"
    original_write = cli_module.new_report

    def write_then_change_source(destination, content, protected):
        original_write(destination, content, protected)
        (tmp_path / "source.mid").write_bytes(b"concurrent synthetic source edit")

    monkeypatch.setattr(cli_module, "new_report", write_then_change_source)
    result = CliRunner().invoke(app, ["plan-midi-performance", str(path), "--output", str(output)])
    assert result.exit_code == 1
    assert "source verified" not in result.output
    assert output.exists()  # Failed new artifact remains diagnostic evidence, never reused.


def test_first_explicit_tempo_after_zero_integrates_the_default_interval(tmp_path):
    make_arrangement(tmp_path)
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(source)
    midi.tracks[0].pop(0)
    midi.save(source)
    result = planner()(save_arrangement(tmp_path, [MidiFileImporter().import_file(source)]))
    assert result.tempos[0].source.is_default and result.tempos[0].source.tick == 0
    assert result.tempos[1].source.tick == 480 and not result.tempos[1].source.is_default
    assert rational(result.tempos[1].position.elapsed_microseconds) == (500000, 1)
    assert rational(result.notes[0].end.elapsed_microseconds) == (1100000, 1)
    assert result.event_type_counts["set_tempo"] == 1
