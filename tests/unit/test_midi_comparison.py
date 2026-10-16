"""Independent synthetic streams catch lost/added events and altered exact clocks."""

import json
from fractions import Fraction

import mido
import pytest
from typer.testing import CliRunner

from suno2flp.cli import app


def compare(*args):
    from suno2flp.validator.midi_comparison import compare_midi_events

    return compare_midi_events(*args)


def save(path, tracks, ppq=96):
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)
    midi.tracks = [mido.MidiTrack(events) for events in tracks]
    midi.save(path)
    return path


def song(path, *, ppq=96, change=96, tempo=1000000, extras=()):
    return save(
        path,
        [
            [
                mido.MetaMessage("set_tempo", tempo=500000),
                mido.MetaMessage("set_tempo", tempo=tempo, time=change),
                mido.MetaMessage("end_of_track", time=4 * ppq - change),
            ],
            [
                mido.Message("program_change", channel=3, program=40),
                *extras,
                mido.Message("note_on", channel=3, note=60, velocity=100, time=2 * ppq),
                mido.Message("note_off", channel=3, note=60, velocity=64, time=ppq),
                mido.MetaMessage("end_of_track", time=ppq),
            ],
        ],
        ppq,
    )


def fraction(value):
    return Fraction(value.numerator, value.denominator)


def test_exact_ppq_conversion_preserves_decoded_events_and_clock(tmp_path):
    a = song(tmp_path / "a.mid")
    b = song(tmp_path / "b.mid", ppq=960, change=960)
    before = (a.read_bytes(), b.read_bytes())
    report = compare(a, b)
    assert report.equivalent and report.events_equal and report.ordered_tracks_equal
    assert report.clock_equal is True
    assert fraction(report.maximum_clock_error_microseconds) == 0
    assert len(report.matches) == 7 and not report.missing and not report.extra
    assert report.expected.tracks[1].events[1].tick == 192
    assert report.candidate.tracks[1].events[1].tick == 1920
    assert report.execution_allowed is False and report.writer_eligibility == "blocked"
    assert before == (a.read_bytes(), b.read_bytes())


@pytest.mark.parametrize("change,sign", [(95, 1), (97, -1)])
def test_one_tick_tempo_shift_is_detected_even_with_identical_notes(tmp_path, change, sign):
    report = compare(song(tmp_path / "a.mid"), song(tmp_path / "b.mid", change=change))
    assert not report.equivalent and report.clock_equal is False
    assert fraction(report.maximum_clock_error_microseconds) == Fraction(15625, 3)
    assert fraction(report.clock_differences[-1].candidate_minus_expected_microseconds) == (
        sign * Fraction(15625, 3)
    )
    assert len(report.missing) == len(report.extra) == 1
    assert report.missing[0].event_index == report.extra[0].event_index == 1


def test_transport_flush_duplicates_and_tail_messages_are_not_deduplicated(tmp_path):
    cc = mido.Message("control_change", channel=3, control=7, value=100)
    a = song(tmp_path / "a.mid", extras=[cc])
    b = song(tmp_path / "b.mid", extras=[cc, cc.copy()])
    report = compare(a, b)
    assert report.clock_equal is True and not report.events_equal
    assert len(report.extra) == 1 and not report.missing
    assert report.extra[0].track_position == 1 and report.extra[0].event_index == 2
    midi = mido.MidiFile(b)
    midi.tracks[1].insert(-1, cc.copy(time=96))
    midi.tracks[1][-1].time = 0
    midi.save(b)
    report = compare(a, b)
    assert len(report.extra) == 2
    assert report.candidate.tracks[1].events[5].tick == 384


def test_same_tick_control_order_change_does_not_pass_multiset_comparison(tmp_path):
    controls = [mido.Message("control_change", control=0, value=v) for v in (1, 2)]
    a = save(tmp_path / "a.mid", [controls])
    b = save(tmp_path / "b.mid", [list(reversed(controls))])
    report = compare(a, b)
    assert report.events_equal and not report.ordered_tracks_equal and not report.equivalent
    assert [m.candidate.event_index for m in report.matches[:2]] == [1, 0]


def test_track_relocation_is_reported_separately_from_event_content(tmp_path):
    tracks = [[mido.Message("program_change", channel=c, program=c)] for c in (0, 1)]
    report = compare(
        save(tmp_path / "a.mid", tracks), save(tmp_path / "b.mid", list(reversed(tracks)))
    )
    assert report.events_equal and not report.ordered_tracks_equal and not report.equivalent


@pytest.mark.parametrize("field,value", [("channel", 4), ("program", 41)])
def test_program_and_original_channel_changes_are_not_implicitly_remapped(tmp_path, field, value):
    a = song(tmp_path / "a.mid")
    b = song(tmp_path / "b.mid")
    midi = mido.MidiFile(b)
    setattr(midi.tracks[1][0], field, value)
    midi.save(b)
    report = compare(a, b)
    assert not report.equivalent and len(report.missing) == len(report.extra) == 1
    assert report.missing[0].event_index == 0


def test_conflicting_same_tick_tempo_retains_events_but_refuses_clock_claim(tmp_path):
    tracks = [
        [mido.MetaMessage("set_tempo", tempo=500000)],
        [mido.MetaMessage("set_tempo", tempo=1000000)],
    ]
    a = save(tmp_path / "a.mid", tracks)
    report = compare(a, a)
    assert report.events_equal and report.ordered_tracks_equal
    assert report.clock_equal is None and report.maximum_clock_error_microseconds is None
    assert not report.equivalent
    assert "midi_comparison_tempo_conflict" in {d.code for d in report.diagnostics}


def test_repeated_identical_tempos_are_preserved_and_have_an_unambiguous_clock(tmp_path):
    a = save(
        tmp_path / "a.mid",
        [[mido.MetaMessage("set_tempo", tempo=500000)] for _ in range(2)],
    )
    report = compare(a, a)
    assert report.equivalent and len(report.matches) == 4


def test_default_tempo_matches_time_but_added_explicit_event_is_visible(tmp_path):
    a = save(tmp_path / "a.mid", [[mido.MetaMessage("end_of_track", time=96)]])
    b = save(
        tmp_path / "b.mid",
        [[mido.MetaMessage("set_tempo", tempo=500000), mido.MetaMessage("end_of_track", time=96)]],
    )
    report = compare(a, b)
    assert report.clock_equal is True and not report.equivalent and len(report.extra) == 1


def test_unknown_meta_deltas_sysex_and_note_off_representation_remain_visible(tmp_path):
    events = [
        mido.midifiles.meta.UnknownMetaMessage(0x70, data=(1, 2), time=7),
        mido.Message("sysex", data=(1, 2, 3), time=5),
        mido.Message("note_on", note=60, velocity=100),
        mido.Message("note_on", note=60, velocity=0, time=12),
    ]
    a = save(tmp_path / "a.mid", [events])
    b = save(tmp_path / "b.mid", [events])
    report = compare(a, b)
    assert report.equivalent
    assert [e.tick for e in report.expected.tracks[0].events] == [7, 12, 12, 24, 24]
    midi = mido.MidiFile(b)
    midi.tracks[0][3] = mido.Message("note_off", note=60, velocity=0, time=12)
    midi.save(b)
    report = compare(a, b)
    assert not report.events_equal


def test_maximum_clock_error_is_not_hidden_by_later_cancellation(tmp_path):
    def tempos(path, values):
        return save(
            path,
            [
                [
                    mido.MetaMessage("set_tempo", tempo=values[0]),
                    mido.MetaMessage("set_tempo", tempo=values[1], time=96),
                    mido.MetaMessage("end_of_track", time=96),
                ]
            ],
        )

    report = compare(
        tempos(tmp_path / "a.mid", (500000, 500000)), tempos(tmp_path / "b.mid", (600000, 400000))
    )
    assert fraction(report.maximum_clock_error_microseconds) == 100000
    assert len(report.clock_differences) == 1
    assert fraction(report.compared_through_beat) == 2


def test_comparison_replay_rejects_forged_results_and_changed_inputs(tmp_path):
    from suno2flp.validator.midi_comparison import verify_midi_comparison

    a = song(tmp_path / "a.mid")
    b = song(tmp_path / "b.mid", change=95)
    report = compare(a, b)
    output = tmp_path / "report.json"
    output.write_text(report.model_dump_json())
    assert verify_midi_comparison(output) == report
    data = json.loads(output.read_text())
    data["equivalent"] = True
    output.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="replay"):
        verify_midi_comparison(output)
    output.write_text(report.model_dump_json())
    song(b, change=97)
    with pytest.raises(ValueError, match="replay"):
        verify_midi_comparison(output)


def test_cli_difference_is_nonzero_with_new_report_and_successful_replay(tmp_path):
    a = song(tmp_path / "a.mid")
    b = song(tmp_path / "b.mid", change=95)
    out = tmp_path / "report.json"
    runner = CliRunner()
    args = ["compare-midi-events", str(a), str(b), "--output", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 1 and out.exists() and "different" in result.output
    assert runner.invoke(app, ["verify-midi-comparison", str(out)]).exit_code == 0
    assert runner.invoke(app, args).exit_code == 1
    assert (
        runner.invoke(
            app, ["compare-midi-events", str(a), str(a), "--output", str(tmp_path / "equal.json")]
        ).exit_code
        == 0
    )


def test_missing_host_output_cannot_produce_success_or_a_report(tmp_path):
    out = tmp_path / "report.json"
    result = CliRunner().invoke(
        app,
        [
            "compare-midi-events",
            str(song(tmp_path / "a.mid")),
            str(tmp_path / "absent.mid"),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 1 and not out.exists()


def test_source_change_during_report_publication_fails(tmp_path, monkeypatch):
    import suno2flp.cli as cli

    a = song(tmp_path / "a.mid")
    b = song(tmp_path / "b.mid")
    original = cli.new_report

    def mutate(path, content, protected):
        original(path, content, protected)
        song(b, change=95)

    monkeypatch.setattr(cli, "new_report", mutate)
    result = CliRunner().invoke(
        app, ["compare-midi-events", str(a), str(b), "--output", str(tmp_path / "report.json")]
    )
    assert result.exit_code == 1 and "Input changed" in result.output


def test_invalid_tempo_is_not_replaced_with_a_successful_default_clock(tmp_path):
    path = save(tmp_path / "invalid.mid", [[mido.MetaMessage("set_tempo", tempo=0)]])
    report = compare(path, path)
    assert report.clock_equal is None and report.maximum_clock_error_microseconds is None
    assert not report.equivalent
    assert any(d.code == "invalid_tempo" for d in report.diagnostics)


def test_change_between_capture_and_import_is_rejected(tmp_path, monkeypatch):
    from suno2flp.importer import MidiFileImporter

    a = song(tmp_path / "a.mid")
    b = song(tmp_path / "b.mid")
    original = MidiFileImporter.import_file

    def changed(self, path):
        if path == b:
            song(b, change=95)
        return original(self, path)

    monkeypatch.setattr(MidiFileImporter, "import_file", changed)
    with pytest.raises(ValueError, match="Input changed"):
        compare(a, b)
