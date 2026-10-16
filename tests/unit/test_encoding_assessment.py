"""Encoding feasibility is analysis, never permission to round or route events."""

import json
from fractions import Fraction

import mido
import pytest
from typer.testing import CliRunner

from suno2flp.arrangement import FaithfulArrangementEngine
from suno2flp.cli import app
from suno2flp.core.models import MusicalMetadata
from suno2flp.flp_builder.performance import plan_performance_file
from suno2flp.importer import MidiFileImporter


def performance(tmp_path, *, tempo=434300, second_source=False, second_tempo=500000):
    sources = []
    for index in range(2 if second_source else 1):
        midi = mido.MidiFile(type=1, ticks_per_beat=480)
        midi.tracks.append(
            mido.MidiTrack(
                [
                    mido.MetaMessage("set_tempo", tempo=tempo),
                    mido.MetaMessage("set_tempo", tempo=second_tempo, time=480),
                    mido.MetaMessage("end_of_track", time=480),
                ]
            )
        )
        midi.tracks.append(
            mido.MidiTrack(
                [
                    mido.Message("program_change", channel=3, program=65 + index),
                    mido.Message("note_on", channel=3, note=60, velocity=90),
                    mido.Message("note_off", channel=3, note=60, time=960),
                    mido.Message("control_change", channel=3, control=7, value=100),
                ]
            )
        )
        midi.tracks.append(
            mido.MidiTrack(
                [
                    mido.Message("program_change", channel=3, program=65 + index),
                    mido.Message("control_change", channel=3, control=7, value=100, time=960),
                    mido.Message("sysex", data=(1, 2, 3)),
                ]
            )
        )
        path = tmp_path / f"{index}.mid"
        midi.save(path)
        sources.append(MidiFileImporter().import_file(path))
    arrangement = FaithfulArrangementEngine().arrange(sources, MusicalMetadata(), "faithful")
    ap = tmp_path / "arrangement.json"
    ap.write_text(arrangement.model_dump_json(), encoding="utf8")
    pp = tmp_path / "performance.json"
    pp.write_text(plan_performance_file(ap).model_dump_json(), encoding="utf8")
    return pp


def assessor():
    from suno2flp.flp_builder.encoding_assessment import assess_encoding_file

    return assess_encoding_file


def frac(value):
    return Fraction(value.numerator, value.denominator)


def test_quantifies_integer_precision_without_rounding_sources(tmp_path):
    pp = performance(tmp_path)
    before = pp.read_bytes()
    r = assessor()(pp)
    first = r.tempos[0]
    assert first.hypothetical_nearest_millibpm == 138153
    assert frac(first.period_error_microseconds) == Fraction(60_000_000_000, 138153) - 434300
    assert frac(r.hypothetical_end_error_microseconds) == frac(first.period_error_microseconds)
    assert frac(r.maximum_boundary_error_microseconds) == abs(frac(first.period_error_microseconds))
    assert first.exact is False
    assert r.execution_allowed is False and r.writer_eligibility == "blocked"
    assert pp.read_bytes() == before


def test_exact_scalars_still_cannot_authorize_host_timing_or_routing(tmp_path):
    r = assessor()(performance(tmp_path, tempo=600000))
    assert all(t.exact for t in r.tempos)
    assert frac(r.hypothetical_end_error_microseconds) == 0
    assert {"encoding_step_timing_unverified", "encoding_destination_unverified"} <= {
        d.code for d in r.diagnostics
    }
    assert r.execution_allowed is False


def test_error_sign_and_interior_boundary_are_not_hidden_by_cancellation(tmp_path):
    r = assessor()(performance(tmp_path, second_tempo=500001))
    first = Fraction(60_000_000_000, 138153) - 434300
    assert frac(r.tempos[1].period_error_microseconds) == -1
    assert frac(r.hypothetical_end_error_microseconds) == first - 1
    assert frac(r.maximum_boundary_error_microseconds) == abs(first)


def test_same_channels_across_inputs_and_duplicate_events_stay_distinct(tmp_path):
    r = assessor()(performance(tmp_path, second_source=True))
    assert [(g.source_input, g.source_channel) for g in r.routes] == [(0, 3), (1, 3)]
    for g in r.routes:
        assert g.source_track_positions == [1, 2]
        assert g.channel_event_count == 6
        assert len(g.controls) == 4
        assert [e.message["type"] for e in g.controls] == [
            "program_change",
            "control_change",
            "program_change",
            "control_change",
        ]
        assert len(g.cross_track_same_tick_groups) == 2
        assert g.destination is None and g.status == "unverified"
        assert g.controls[1].source_tick == 960
        assert g.controls[1].position.target_tick.numerator == 960
    assert len(r.nonchannel_events) == 2
    assert r.nonchannel_events[0].message == {"type": "sysex", "data": [1, 2, 3], "time": 0}
    assert r.reused_source_channels == [3]


@pytest.mark.parametrize("tempo", [1, 16777215])
def test_out_of_observed_scalar_range_has_no_simulated_schedule(tmp_path, tempo):
    r = assessor()(performance(tmp_path, tempo=tempo))
    assert r.hypothetical_end_error_microseconds is None
    assert r.tempos[0].hypothetical_nearest_millibpm is None


def test_forged_performance_rejected(tmp_path):
    pp = performance(tmp_path)
    data = json.loads(pp.read_text())
    data["tempos"][0]["exact_milli_bpm"] = 120000
    pp.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="replay"):
        assessor()(pp)


def test_saved_assessment_replays_and_rejects_modified_claims(tmp_path):
    from suno2flp.flp_builder.encoding_assessment import verify_encoding_file

    pp = performance(tmp_path)
    r = assessor()(pp)
    saved = tmp_path / "assessment.json"
    saved.write_text(r.model_dump_json(), encoding="utf8")
    assert verify_encoding_file(saved) == r
    data = json.loads(saved.read_text())
    data["routes"][0]["controls"].reverse()
    saved.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="replay"):
        verify_encoding_file(saved)


def test_cli_new_output_and_replay(tmp_path):
    pp = performance(tmp_path)
    out = tmp_path / "assessment.json"
    runner = CliRunner()
    args = ["assess-midi-encoding", str(pp), "--output", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "blocked" in result.output
    assert runner.invoke(app, ["verify-midi-encoding", str(out)]).exit_code == 0
    assert runner.invoke(app, args).exit_code == 1


def test_current_midi_change_rejects_saved_assessment(tmp_path):
    from suno2flp.flp_builder.encoding_assessment import verify_encoding_file

    pp = performance(tmp_path)
    saved = tmp_path / "assessment.json"
    saved.write_text(assessor()(pp).model_dump_json(), encoding="utf8")
    midi = mido.MidiFile(tmp_path / "0.mid")
    midi.tracks[1][0].program = 1
    midi.save(tmp_path / "0.mid")
    with pytest.raises(ValueError, match="replay"):
        verify_encoding_file(saved)


def test_assessment_source_change_during_publication_fails(tmp_path, monkeypatch):
    import suno2flp.cli as cli

    pp = performance(tmp_path)
    original = cli.new_report

    def change_after(path, content, protected):
        original(path, content, protected)
        pp.write_text("{}", encoding="utf8")

    monkeypatch.setattr(cli, "new_report", change_after)
    result = CliRunner().invoke(
        app, ["assess-midi-encoding", str(pp), "--output", str(tmp_path / "report.json")]
    )
    assert result.exit_code == 1 and "Input changed" in result.output
