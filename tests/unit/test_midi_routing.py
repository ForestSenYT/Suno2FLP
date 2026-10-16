"""Explicit routes cannot drop occurrences, alias receivers or authorize a writer."""

import json

import mido
import pytest
from typer.testing import CliRunner

from suno2flp.arrangement import FaithfulArrangementEngine
from suno2flp.cli import app
from suno2flp.core.errors import OfflineError
from suno2flp.core.models import MusicalMetadata
from suno2flp.flp_builder.encoding_assessment import assess_encoding_file
from suno2flp.flp_builder.performance import plan_performance_file
from suno2flp.importer import MidiFileImporter


@pytest.fixture
def inputs(tmp_path):
    sources = []
    for index, channels in enumerate(((3, 3, 9), (3,))):
        midi = mido.MidiFile(type=1, ticks_per_beat=480)
        midi.tracks.append(
            mido.MidiTrack(
                [
                    mido.MetaMessage("set_tempo", tempo=500001),
                    mido.MetaMessage("set_tempo", tempo=500000, time=480),
                ]
            )
        )
        for channel in channels:
            midi.tracks.append(
                mido.MidiTrack(
                    [
                        mido.Message("program_change", channel=channel, program=42 + index),
                        mido.Message("note_on", channel=channel, note=60, velocity=90),
                        mido.Message("note_off", channel=channel, note=60, time=960),
                        mido.Message("control_change", channel=channel, control=7, value=100),
                        mido.Message("sysex", data=(1, 2)),
                    ]
                )
            )
        source = tmp_path / f"{index}.mid"
        midi.save(source)
        sources.append(MidiFileImporter().import_file(source))
    arrangement = FaithfulArrangementEngine().arrange(sources, MusicalMetadata(), "faithful")
    ap = tmp_path / "arrangement.json"
    ap.write_text(arrangement.model_dump_json(), encoding="utf-8")
    pp = tmp_path / "performance.json"
    pp.write_text(plan_performance_file(ap, target_ppq=960).model_dump_json(), encoding="utf-8")
    rows = [
        dict(
            source_input=i,
            source_channel=c,
            destination_port=16 + i,
            destination_channel=c,
            receiver_id=f"receiver-{i}",
        )
        for i, c in ((0, 3), (0, 9), (1, 3))
    ]
    bp = tmp_path / "bindings.json"
    bp.write_text(json.dumps(dict(schema_version=1, bindings=rows)), encoding="utf-8")
    return pp, bp, rows


def planner():
    from suno2flp.flp_builder.midi_routing import plan_midi_routing_file

    return plan_midi_routing_file


def verifier():
    from suno2flp.flp_builder.midi_routing import verify_midi_routing_file

    return verify_midi_routing_file


def change(bp, rows):
    bp.write_text(json.dumps(dict(schema_version=1, bindings=rows)), encoding="utf-8")


def test_complete_routes_keep_all_controls_exact_positions_and_pending_gates(inputs):
    pp, bp, rows = inputs
    before = {p: p.read_bytes() for p in pp.parent.iterdir() if p.is_file()}
    expected = assess_encoding_file(pp)
    report = planner()(pp, bp)
    assert report.assessment == expected
    assert [r.source for r in report.routes] == expected.routes
    assert [r.binding.model_dump() for r in report.routes] == rows
    controls = report.routes[0].source.controls
    assert [c.message["type"] for c in controls] == [
        "program_change",
        "control_change",
        "program_change",
        "control_change",
    ]
    assert [c.source_tick for c in controls] == [0, 960, 0, 960]
    assert [c.position.target_tick.numerator for c in controls] == [0, 1920, 0, 1920]
    assert len(report.assessment.nonchannel_events) >= 4
    assert report.coverage_complete is True
    assert report.receiver_delivery == "unverified" and report.execution_allowed is False
    assert report.writer_eligibility == "blocked"
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("kind", ["missing", "extra", "duplicate"])
def test_exact_source_coverage_required(inputs, kind):
    pp, bp, rows = inputs
    if kind == "missing":
        rows.pop()
    elif kind == "extra":
        rows.append(
            {**rows[-1], "source_input": 99, "destination_port": 99, "receiver_id": "extra"}
        )
    else:
        rows.append(rows[0])
    change(bp, rows)
    with pytest.raises(ValueError, match="coverage|Duplicate source"):
        planner()(pp, bp)


def test_distinct_sources_cannot_alias_same_destination(inputs):
    pp, bp, rows = inputs
    rows[-1].update(destination_port=16, receiver_id="receiver-0")
    change(bp, rows)
    with pytest.raises(ValueError, match="destination"):
        planner()(pp, bp)


@pytest.mark.parametrize("kind", ["two_receivers_one_port", "one_receiver_two_ports"])
def test_receiver_port_namespace_is_unambiguous(inputs, kind):
    pp, bp, rows = inputs
    if kind == "two_receivers_one_port":
        rows[1]["receiver_id"] = "different"
    else:
        rows[1]["destination_port"] = 19
    change(bp, rows)
    with pytest.raises(ValueError, match="receiver.*port|port.*receiver"):
        planner()(pp, bp)


def test_channel_rewriting_is_rejected(inputs):
    pp, bp, rows = inputs
    rows[0]["destination_channel"] = 2
    change(bp, rows)
    with pytest.raises(ValueError, match="channel"):
        planner()(pp, bp)


@pytest.mark.parametrize("bad", [True, "16", -1, 256, 1.5])
def test_port_requires_bounded_integer(inputs, bad):
    pp, bp, rows = inputs
    rows[0]["destination_port"] = bad
    change(bp, rows)
    with pytest.raises(ValueError):
        planner()(pp, bp)


def test_duplicate_json_keys_are_not_silently_accepted(inputs):
    pp, bp, _ = inputs
    bp.write_text('{"schema_version":1,"bindings":[],"bindings":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON"):
        planner()(pp, bp)


def test_binding_document_order_is_retained_without_reordering_sources(inputs):
    pp, bp, rows = inputs
    change(bp, list(reversed(rows)))
    report = planner()(pp, bp)
    assert [b.source_input for b in report.config.bindings] == [1, 0, 0]
    assert [r.binding.source_input for r in report.routes] == [0, 0, 1]


@pytest.mark.parametrize("kind", ["saved_control", "config", "source", "execution"])
def test_saved_plan_replays_all_current_inputs_and_fields(inputs, kind):
    pp, bp, rows = inputs
    report = planner()(pp, bp)
    path = pp.parent / "routing.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    assert verifier()(path) == report
    if kind == "saved_control":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["routes"][0]["source"]["controls"][0]["message"]["program"] = 0
        path.write_text(json.dumps(data), encoding="utf-8")
    elif kind == "config":
        rows[-1]["destination_port"] = 25
        change(bp, rows)
    elif kind == "source":
        midi = mido.MidiFile(pp.parent / "0.mid")
        midi.tracks[1][0].program = 50
        midi.save(pp.parent / "0.mid")
    else:
        path.write_text(
            report.model_dump_json().replace(
                '"execution_allowed":false', '"execution_allowed":true'
            ),
            encoding="utf-8",
        )
    with pytest.raises((ValueError, RuntimeError)):
        verifier()(path)


def test_cli_publication_is_exclusive_and_validation_is_not_execution(inputs):
    pp, bp, rows = inputs
    out = pp.parent / "routing.json"
    runner = CliRunner()
    args = ["plan-midi-routing", str(pp), str(bp), "--output", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "receiver unverified" in result.output and "blocked" in result.output
    assert runner.invoke(app, ["verify-midi-routing", str(out)]).exit_code == 0
    assert runner.invoke(app, args).exit_code == 1
    rows.pop()
    change(bp, rows)
    args[-1] = str(pp.parent / "invalid.json")
    assert runner.invoke(app, args).exit_code == 1
    assert not (pp.parent / "invalid.json").exists()
    assert not list(pp.parent.glob("*.flp"))


def test_binding_change_during_planning_cannot_publish_success(inputs, monkeypatch):
    from suno2flp.flp_builder import midi_routing

    pp, bp, rows = inputs
    real_assess = midi_routing.assess_encoding_file

    def changing_assess(path):
        result = real_assess(path)
        rows[-1]["destination_port"] = 25
        change(bp, rows)
        return result

    monkeypatch.setattr(midi_routing, "assess_encoding_file", changing_assess)
    with pytest.raises(OfflineError, match="offline_input_changed"):
        planner()(pp, bp)


def test_report_cannot_replace_binding_or_input_file(inputs):
    pp, bp, _ = inputs
    runner = CliRunner()
    before = {p: p.read_bytes() for p in (pp, bp, pp.parent / "0.mid")}
    for destination in before:
        result = runner.invoke(
            app, ["plan-midi-routing", str(pp), str(bp), "--output", str(destination)]
        )
        assert result.exit_code == 1
    assert all(p.read_bytes() == raw for p, raw in before.items())
