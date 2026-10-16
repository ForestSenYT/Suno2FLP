"""Original synthetic readiness evidence; never distributes private template bytes."""

import hashlib
import json
import struct

import pytest
from test_build_planning import planning_case as planning_case
from test_build_planning import replace_inventory, template_bytes
from test_fl26_inventory import event

from suno2flp.core.errors import BuildPlanningError, Suno2FLPError
from suno2flp.core.template_summary import compare_backend_summary


@pytest.fixture
def readiness_case(planning_case):
    def make(*, extra=b"", **options):
        arrangement, inspection, bindings, backend = planning_case(**options)
        raw = template_bytes(version="26.1.7.5654", stride=88, extra=extra)
        replace_inventory(inspection, bindings, raw)
        inspection.project.fl_studio_version = "26.1.7.5654"
        inspection.project.patterns = []
        inspection.project.playlist_item_count = 0
        inspection.project.tempo = 140
        local, status, mismatches = compare_backend_summary(
            inspection.inventory, inspection.project
        )
        inspection.local_summary = local
        inspection.backend_summary_status = status
        inspection.backend_summary_mismatches = mismatches
        return arrangement, inspection, bindings, backend

    return make


def assess(inspection, arrangement=None, bindings=None):
    from suno2flp.flp_builder.assessment import assess_template

    return assess_template(inspection.template_path.read_bytes(), inspection, arrangement, bindings)


def test_dependency_manifest_is_byte_linked_without_resolving_sample_paths(
    readiness_case, monkeypatch
):
    sample = "%FACTORY%/../unavailable.wav"
    extra = event(64, b"\0\0") + event(201, "FLEX\0".encode("utf-16-le"))
    extra += event(203, "任意显示名\0".encode("utf-16-le"))
    extra += event(196, (sample + "\0").encode("utf-16-le"))
    extra += event(212, b"original-init") + event(213, b"original-state")
    _, inspection, _, _ = readiness_case(extra=extra)
    raw = inspection.template_path.read_bytes()
    from suno2flp.flp_builder.assessment import assess_template

    monkeypatch.setattr(
        "pathlib.Path.read_bytes", lambda *_: pytest.fail("pure assessment read a file")
    )
    report = assess_template(raw, inspection)
    assert [d.kind for d in report.dependencies] == [
        "generator_declaration",
        "display_name",
        "sample_reference",
        "plugin_initialization",
        "plugin_state",
    ]
    assert report.dependencies[0].text == "FLEX"
    assert report.dependencies[1].text == "任意显示名"
    assert report.dependencies[2].text == sample
    for item in report.dependencies:
        e = report.inspection.inventory.events[item.event_index]
        assert item.payload_sha256 == e.payload_sha256
        assert item.file_offset == e.payload_offset
        assert item.payload_size == e.payload_size
        assert item.owner_verified is False and item.availability == "unverified"
        assert item.version is None and item.rights == "unverified"
    assert report.execution_allowed is False and report.writer_status == "blocked"
    assert report.binding_check is None


@pytest.mark.parametrize(
    "payload,status,text",
    [(b"\0\0", "empty", ""), (b"x", "invalid", None), (b"\0\xd8", "invalid", None)],
)
def test_empty_and_invalid_text_preserves_raw_evidence(readiness_case, payload, status, text):
    _, inspection, _, _ = readiness_case(extra=event(201, payload))
    item = assess(inspection).dependencies[0]
    assert item.text_status == status and item.text == text
    assert item.raw_text_hex == payload.hex()
    assert item.payload_sha256 == hashlib.sha256(payload).hexdigest()


def test_mixer_plugin_is_not_assigned_to_stale_rack_channel(readiness_case):
    extra = event(64, b"\x01\0") + event(201, "FLEX\0".encode("utf-16-le"))
    extra += event(98, b"\0\0") + event(201, "Effect\0".encode("utf-16-le"))
    extra += event(213, b"a") + event(213, b"b")
    _, inspection, _, _ = readiness_case(extra=extra)
    deps = assess(inspection).dependencies
    assert [d.channel_context for d in deps] == [1, None, None, None]
    assert [d.payload_sha256 for d in deps[-2:]] == [
        hashlib.sha256(x).hexdigest() for x in (b"a", b"b")
    ]
    assert all(d.owner_verified is False for d in deps)


def test_unresolved_records_are_retained_without_duration_or_crop_inference(readiness_case):
    _, inspection, bindings, _ = readiness_case()
    raw = bytearray(inspection.template_path.read_bytes())
    note = inspection.inventory.notes[0]
    raw[note.file_offset + 4 : note.file_offset + 6] = struct.pack("<H", 0x4000)
    raw[note.file_offset + 8 : note.file_offset + 12] = b"\0" * 4
    clip = inspection.inventory.clips[0]
    raw[clip.file_offset + 24 : clip.file_offset + 32] = b"\xff" * 8
    replace_inventory(inspection, bindings, bytes(raw))
    local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
    (
        inspection.local_summary,
        inspection.backend_summary_status,
        inspection.backend_summary_mismatches,
    ) = local, status, mismatch
    report = assess(inspection)
    codes = {f.code for f in report.findings}
    assert {
        "note_duration_unresolved",
        "note_attributes_unresolved",
        "crop_semantics_unresolved",
        "clip_extension_unresolved",
        "backend_summary_inconsistent",
    } <= codes
    assert report.inspection.inventory.notes[0].length_ticks == 0
    assert report.inspection.inventory.clips[0].start_offset.raw_hex == "ffffffff"
    assert report.inspection.inventory.clips[0].extension_hex == "0" * 16
    assert all(g.status != "passed" for g in report.writer_gates)


def test_local_bindings_match_even_when_backend_omits_patterns_but_never_enable_execution(
    readiness_case,
):
    arrangement, inspection, bindings, _ = readiness_case()
    before = (
        arrangement.model_dump_json(),
        inspection.model_dump_json(),
        bindings.model_dump_json(),
    )
    report = assess(inspection, arrangement, bindings)
    check = report.binding_check
    assert check.status == "matched" and check.instrument_intent == "unverified"
    assert check.arrangement == arrangement and check.bindings == bindings
    assert [p.notes[0].source_channel for p in check.parts] == [2, 9]
    assert (check.parts[0].notes[0].start_tick, check.parts[0].notes[0].duration_ticks) == (24, 48)
    assert check.parts[0].template_note_indices == [0] and check.parts[0].template_clip_indices == [
        0
    ]
    assert check.arrangement.sources[0].midi.tracks[1].notes[0].start_tick == 120
    assert report.inspection.project.patterns == []
    assert report.writer_status == "blocked" and report.execution_allowed is False
    assert before == (
        arrangement.model_dump_json(),
        inspection.model_dump_json(),
        bindings.model_dump_json(),
    )
    from suno2flp.core.assessment_models import TemplateReadinessReport

    assert TemplateReadinessReport.model_validate_json(report.model_dump_json()) == report


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("template_channel_id", 1, "binding_local_note_pair_missing"),
        ("template_pattern_id", 30, "binding_local_note_pair_missing"),
        ("template_playlist_track", 9, "binding_local_clip_missing"),
        ("source_channel", 3, "binding_source_missing"),
    ],
)
def test_wrong_local_targets_are_explicit_blocked_evidence(readiness_case, field, value, code):
    arrangement, inspection, bindings, _ = readiness_case()
    bindings.config.bindings.pop()
    setattr(bindings.config.bindings[0], field, value)
    report = assess(inspection, arrangement, bindings)
    assert report.binding_check.status == "blocked"
    assert code in {d.code for d in report.binding_check.diagnostics}


@pytest.mark.parametrize("options", [{"start": 1}, {"duration": 1}])
def test_inexact_ppq_has_no_partial_note_preview(readiness_case, options):
    arrangement, inspection, bindings, _ = readiness_case(**options)
    check = assess(inspection, arrangement, bindings).binding_check
    assert check.status == "blocked" and check.parts[0].notes is None
    assert "ppq_inexact" in {d.code for d in check.diagnostics}


def test_empty_bindings_retain_unbound_sources(readiness_case):
    arrangement, inspection, bindings, _ = readiness_case()
    bindings.config.bindings.clear()
    check = assess(inspection, arrangement, bindings).binding_check
    assert check.status == "blocked" and len(check.unbound_sources) == 2 and check.parts == []


@pytest.mark.parametrize(
    "changed",
    [
        "arrangement",
        "comparison",
        "inventory",
        "raw",
        "binding_identity",
        "version",
        "missing_inventory",
    ],
)
def test_tampered_or_unsupported_evidence_is_refused(readiness_case, changed):
    arrangement, inspection, bindings, _ = readiness_case()
    if changed == "arrangement":
        arrangement.tracks[1].notes[0].start_tick += 1
    elif changed == "comparison":
        inspection.backend_summary_status = "consistent"
    elif changed == "inventory":
        inspection.inventory.events[0].payload_sha256 = "0" * 64
    elif changed == "raw":
        inspection.template_path.write_bytes(inspection.template_path.read_bytes() + b"x")
    elif changed == "binding_identity":
        bindings.config.template_sha256 = "0" * 64
    elif changed == "version":
        replace_inventory(inspection, bindings, template_bytes())
    else:
        inspection.inventory = None
    with pytest.raises((Suno2FLPError, ValueError)):
        assess(inspection, arrangement, bindings)


def test_paired_binding_arguments_are_required(readiness_case):
    arrangement, inspection, _, _ = readiness_case()
    with pytest.raises(BuildPlanningError, match="assessment_inputs_incomplete"):
        assess(inspection, arrangement)


def save_inputs(tmp_path, case):
    arrangement, inspection, bindings, backend = case
    a, i, b = (tmp_path / name for name in ("arrangement.json", "inspection.json", "bindings.yaml"))
    a.write_text(arrangement.model_dump_json(), encoding="utf-8")
    i.write_text(inspection.model_dump_json(), encoding="utf-8")
    b.write_text(json.dumps(bindings.config.model_dump(mode="json")), encoding="utf-8")
    return a, i, b, backend


def test_file_assessment_is_process_free_and_preserves_full_input_hashes(
    tmp_path, readiness_case, monkeypatch
):
    from suno2flp.flp_builder.assessment_files import assess_template_files

    case = readiness_case()
    a, i, b, backend = save_inputs(tmp_path, case)
    path = case[1].template_path
    before = path.read_bytes(), path.stat().st_mtime_ns
    monkeypatch.setattr("subprocess.run", lambda *_args, **_kwargs: pytest.fail("process invoked"))
    result = assess_template_files(i, backend, a, b)
    assert result.binding_check.status == "matched"
    assert {f.kind for f in result.input_files} == {"arrangement", "inspection", "bindings"}
    for f in result.input_files:
        assert f.sha256 == hashlib.sha256(f.path.read_bytes()).hexdigest()
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert result.template_mtime_ns_before == result.template_mtime_ns_after == before[1]


@pytest.mark.parametrize("target", ["existing", "source", "backend", "flp", "ads"])
def test_cli_refuses_unsafe_destinations(tmp_path, readiness_case, target):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    case = readiness_case()
    _, i, _, backend = save_inputs(tmp_path, case)
    destination = {
        "existing": i,
        "source": case[1].template_path,
        "backend": backend / "report.json",
        "flp": tmp_path / "new.flp",
        "ads": str(i) + ":report.json",
    }[target]
    original = case[1].template_path.read_bytes()
    result = CliRunner().invoke(
        app,
        ["assess-template", str(i), "--backend-dir", str(backend), "--output", str(destination)],
    )
    assert result.exit_code == 1 and "new .json" in result.output
    assert case[1].template_path.read_bytes() == original


def test_cli_json_is_deterministic_and_blocked_is_a_successful_read_only_assessment(
    tmp_path, readiness_case
):
    from typer.testing import CliRunner

    from suno2flp.cli import app
    from suno2flp.core.assessment_models import TemplateReadinessReport

    a, i, b, backend = save_inputs(tmp_path, readiness_case())
    args = [
        "assess-template",
        str(i),
        "--backend-dir",
        str(backend),
        "--arrangement",
        str(a),
        "--bindings",
        str(b),
    ]
    runner = CliRunner()
    first, second = runner.invoke(app, args), runner.invoke(app, args)
    assert first.exit_code == second.exit_code == 0
    assert first.stdout == second.stdout
    parsed = TemplateReadinessReport.model_validate_json(first.stdout)
    assert parsed.writer_status == "blocked" and parsed.binding_check.status == "matched"
    output = tmp_path / "report.json"
    assert runner.invoke(app, [*args, "--output", str(output)]).exit_code == 0
    assert TemplateReadinessReport.model_validate_json(output.read_text()) == parsed


@pytest.mark.parametrize("changed", ["template", "backend", "timestamp"])
def test_file_failure_path_rechecks_original_and_backend(
    tmp_path, readiness_case, monkeypatch, changed
):
    import os

    from suno2flp.flp_builder import assessment_files

    case = readiness_case()
    a, i, b, backend = save_inputs(tmp_path, case)
    template = case[1].template_path

    def failure(*args):
        if changed == "template":
            template.write_bytes(b"test-only concurrent change")
        elif changed == "backend":
            (backend / "publish/music2daw.dll").write_bytes(b"test-only change")
        else:
            stat = template.stat()
            os.utime(template, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        raise RuntimeError("assessment failed")

    monkeypatch.setattr(assessment_files, "assess_template", failure)
    expected = {
        "template": "template_snapshot_stale",
        "backend": "backend_integrity_failed",
        "timestamp": "template_timestamp_changed",
    }[changed]
    with pytest.raises(Suno2FLPError, match=expected):
        assessment_files.assess_template_files(i, backend, a, b)


@pytest.mark.parametrize("changed", ["text", "missing", "link"])
def test_json_dependency_tampering_is_rejected(readiness_case, changed):
    from pydantic import ValidationError

    from suno2flp.core.assessment_models import TemplateReadinessReport

    _, inspection, _, _ = readiness_case(extra=event(201, "FLEX\0".encode("utf-16-le")))
    data = json.loads(assess(inspection).model_dump_json())
    if changed == "text":
        data["dependencies"][0]["text"] = "Other plugin"
    elif changed == "missing":
        data["dependencies"].clear()
    else:
        data["dependencies"][0]["file_offset"] += 1
    with pytest.raises(ValidationError):
        TemplateReadinessReport.model_validate(data)


def test_binding_ambiguous_local_clip_does_not_report_a_match(readiness_case):
    arrangement, inspection, bindings, _ = readiness_case()
    raw = inspection.template_path.read_bytes()
    last = inspection.inventory.events[-1]
    payload = raw[last.payload_offset : last.payload_offset + last.payload_size]
    events = raw[22 : last.file_offset] + event(233, payload[:88] + payload)
    new_raw = raw[:18] + struct.pack("<I", len(events)) + events
    replace_inventory(inspection, bindings, new_raw)
    local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
    inspection.local_summary = local
    inspection.backend_summary_status = status
    inspection.backend_summary_mismatches = mismatch
    check = assess(inspection, arrangement, bindings).binding_check
    assert check.status == "blocked"
    assert "binding_local_ambiguous" in {d.code for d in check.diagnostics}


def test_file_stale_inspection_creates_no_cli_output(tmp_path, readiness_case):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    case = readiness_case()
    _, i, _, backend = save_inputs(tmp_path, case)
    raw = json.loads(i.read_text())
    raw["inventory"]["events"][0]["payload_sha256"] = "0" * 64
    i.write_text(json.dumps(raw))
    output = tmp_path / "must-not-exist.json"
    result = CliRunner().invoke(
        app, ["assess-template", str(i), "--backend-dir", str(backend), "--output", str(output)]
    )
    assert result.exit_code == 1 and "template_inventory_stale" in result.output
    assert not output.exists()


@pytest.mark.parametrize("changed", ["unclosed", "missing_hash"])
def test_incomplete_source_provenance_blocks_local_match(readiness_case, changed):
    import mido

    from suno2flp.arrangement import FaithfulArrangementEngine
    from suno2flp.importer import MidiFileImporter

    arrangement, inspection, bindings, _ = readiness_case()
    midi = arrangement.sources[0].midi
    if changed == "unclosed":
        source = mido.MidiFile(midi.source)
        source.tracks[1].insert(1, mido.Message("note_on", channel=3, note=65, velocity=100))
        source.save(midi.source)
        midi = MidiFileImporter().import_file(midi.source)
    else:
        midi.source_sha256 = None
    arrangement = FaithfulArrangementEngine().arrange([midi], arrangement.metadata, "faithful")
    check = assess(inspection, arrangement, bindings).binding_check
    assert check.status == "blocked"
    assert {"unclosed": "source_notes_incomplete", "missing_hash": "source_hash_unverified"}[
        changed
    ] in {d.code for d in check.diagnostics}


@pytest.mark.parametrize("kind,payload", [(27, b"\0"), (95, b"\0\0"), (149, b"\0" * 4)])
def test_all_assessed_mixer_boundaries_clear_rack_hint(readiness_case, kind, payload):
    extra = event(64, b"\x01\0") + event(201, "FLEX\0".encode("utf-16-le"))
    extra += event(kind, payload) + event(201, "Effect\0".encode("utf-16-le"))
    _, inspection, _, _ = readiness_case(extra=extra)
    assert [d.channel_context for d in assess(inspection).dependencies] == [1, None]


def test_separate_playlist_events_must_not_be_combined_as_one_target_set(readiness_case):
    arrangement, inspection, bindings, _ = readiness_case()
    raw = inspection.template_path.read_bytes()
    last = inspection.inventory.events[-1]
    payload = raw[last.payload_offset : last.payload_offset + last.payload_size]
    events = raw[22 : last.file_offset] + event(233, payload[:88]) + event(233, payload[88:])
    replace_inventory(inspection, bindings, raw[:18] + struct.pack("<I", len(events)) + events)
    local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
    inspection.local_summary = local
    inspection.backend_summary_status = status
    inspection.backend_summary_mismatches = mismatch
    check = assess(inspection, arrangement, bindings).binding_check
    assert check.status == "blocked"
    assert "binding_local_ambiguous" in {d.code for d in check.diagnostics}


@pytest.mark.parametrize("field", ["inspection", "arrangement"])
def test_recorded_snapshot_hashes_are_validated_on_json_load(readiness_case, field):
    from pydantic import ValidationError

    from suno2flp.core.assessment_models import TemplateReadinessReport

    arrangement, inspection, bindings, _ = readiness_case()
    data = json.loads(assess(inspection, arrangement, bindings).model_dump_json())
    if field == "inspection":
        data["inspection_snapshot_sha256"] = "0" * 64
    else:
        data["binding_check"]["arrangement_snapshot_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="snapshot"):
        TemplateReadinessReport.model_validate(data)
