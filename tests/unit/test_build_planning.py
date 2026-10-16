import hashlib
import json
import struct

import mido
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from suno2flp.arrangement import ExplicitInstrumentMapper, FaithfulArrangementEngine
from suno2flp.cli import app
from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.core.build_config import load_template_bindings
from suno2flp.core.build_models import DryRunBuildPlan, TemplateBindingDocument
from suno2flp.core.errors import BuildPlanningError, ConfigurationError
from suno2flp.core.models import InstrumentAssignment, InstrumentMappingDocument, MusicalMetadata
from suno2flp.flp_builder.planning import DryRunBuildPlanner


def template_bytes(
    ppq=96,
    *,
    slots=2,
    extra=b"",
    crop=0.0,
    muted=False,
    other_notes=False,
    version="25.1.2.4896",
    stride=80,
):
    def data(kind, payload):
        length = len(payload)
        prefix = bytearray([kind])
        while length >= 128:
            prefix.append((length & 127) | 128)
            length >>= 7
        return bytes(prefix) + bytes([length]) + payload

    events = data(199, version.encode() + b"\0") + b"\x9c" + struct.pack("<I", 120000)
    clips = bytearray()
    for index in range(slots):
        record = bytearray(24)
        struct.pack_into("<i", record, 0, 120)
        record[6], record[12], record[20], record[21] = index, 60, 64, 80
        struct.pack_into("<i", record, 8, 48)
        if other_notes and index == 0:
            record[6] = 1
        events += b"\x41" + struct.pack("<H", index + 1) + data(224, record)
        item = bytearray(stride)
        struct.pack_into("<HHiHH", item, 4, slots, slots + index + 1, 192, 499 - index - 4, 0)
        struct.pack_into("<H", item, 18, 0x2000 if muted else 0)
        struct.pack_into("<f", item, 24, crop)
        clips.extend(item)
    events += data(233, clips) + extra
    return (
        b"FLhd"
        + struct.pack("<IHHH", 6, 0, slots, ppq)
        + b"FLdt"
        + struct.pack("<I", len(events))
        + events
    )


def replace_inventory(inspection, bindings, raw):
    from suno2flp.integrations.template_inventory import scan_template_inventory

    inspection.template_path.write_bytes(raw)
    fingerprint = hashlib.sha256(raw).hexdigest()
    inspection.template_sha256_before = inspection.template_sha256_after = fingerprint
    inspection.size_bytes = len(raw)
    inspection.inventory = scan_template_inventory(raw)
    bindings.config.template_sha256 = fingerprint


@pytest.fixture
def planning_case(tmp_path):
    def make(
        *,
        start=120,
        duration=240,
        tempo=500000,
        meter=(4, 4),
        changes=(),
        extra=(),
        target_ppq=96,
        multichannel=False,
    ):
        source = tmp_path / "original.mid"
        midi = mido.MidiFile(type=1, ticks_per_beat=480)
        midi.tracks.extend(
            [
                mido.MidiTrack(
                    [
                        mido.MetaMessage("set_tempo", tempo=tempo),
                        mido.MetaMessage(
                            "time_signature", numerator=meter[0], denominator=meter[1]
                        ),
                        *changes,
                    ]
                ),
                mido.MidiTrack(
                    [
                        mido.MetaMessage("track_name", name="Same name"),
                        *extra,
                        mido.Message("note_on", channel=2, note=60, velocity=80, time=start),
                        mido.Message("note_off", channel=2, note=60, time=duration),
                    ]
                ),
                mido.MidiTrack(
                    [
                        mido.MetaMessage("track_name", name="Same name"),
                        mido.Message("note_on", channel=9, note=36, velocity=90, time=240),
                        mido.Message("note_off", channel=9, note=36, time=120),
                    ]
                ),
            ]
        )
        if multichannel:
            midi.tracks[1] = mido.merge_tracks(midi.tracks[1:])
            midi.tracks.pop()
        midi.save(source)
        from suno2flp.importer import MidiFileImporter

        arrangement = FaithfulArrangementEngine().arrange(
            [MidiFileImporter().import_file(source)], MusicalMetadata(), "faithful"
        )
        backend = tmp_path / "backend"
        backend.mkdir(exist_ok=True)
        files = {}
        for name in [
            "publish/music2daw.dll",
            "publish/music2daw.deps.json",
            "publish/music2daw.runtimeconfig.json",
            "publish/Music2Daw.Core.dll",
            "publish/Monad.FLParser.dll",
            "publish/Melanchall.DryWetMidi.dll",
            "source/LICENSE",
            "source/src/Monad.FLParser/LICENSE",
            "global.json",
            "source/src/Music2Daw.Cli/packages.lock.json",
            "source/src/Music2Daw.Core/packages.lock.json",
            "source/src/Monad.FLParser/packages.lock.json",
            "source/src/Music2Daw.Cli/obj/project.assets.json",
        ]:
            path = backend / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic backend fixture")
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        record = {
            "schema_version": 1,
            "backend": "music2daw",
            "repository": "https://github.com/jihadkhawaja/flstudio-mcp",
            "revision": "6def9463d6fa8636bbc81010581318a39c47d3c4",
            "license": "GPL-3.0-or-later",
            "sdk_version": "10.0.401",
            "packages": {"Melanchall.DryWetMidi": "8.0.3"},
            "files": files,
        }
        (backend / "backend.json").write_text(json.dumps(record))
        template = tmp_path / "original.flp"
        template.write_bytes(template_bytes(target_ppq))
        digest = hashlib.sha256(template.read_bytes()).hexdigest()
        inspection = TemplateInspectionReport.model_validate(
            {
                "template_path": str(template),
                "size_bytes": template.stat().st_size,
                "template_sha256_before": digest,
                "template_sha256_after": digest,
                "backend_manifest_sha256": hashlib.sha256(
                    (backend / "backend.json").read_bytes()
                ).hexdigest(),
                "backend": record,
                "runtime_version": "10.0.12",
                "header": {"format": 0, "channel_count": 2, "ppq": target_ppq},
                "project": {
                    "source_path": str(template),
                    "fl_studio_version": "25.1.2.4896",
                    "tempo": 120,
                    "ppq": target_ppq,
                    "title": "",
                    "author": "",
                    "playlist_item_count": 2,
                    "channels": [
                        {
                            "id": 0,
                            "name": "Same name",
                            "generator": "Sampler",
                            "isLikelySequenced": False,
                        },
                        {
                            "id": 1,
                            "name": "Same name",
                            "generator": "Sampler",
                            "isLikelySequenced": False,
                        },
                    ],
                    "patterns": [
                        {"id": 0, "name": "Same name", "noteCount": 1},
                        {"id": 1, "name": "Same name", "noteCount": 1},
                    ],
                    "inserts": [],
                },
            }
        )
        document = TemplateBindingDocument.model_validate(
            {
                "config": {
                    "template_sha256": digest,
                    "backend_revision": record["revision"],
                    "bindings": [
                        {
                            "source_input": 0,
                            "source_track_position": 1,
                            "source_channel": 2,
                            "template_channel_id": 0,
                            "template_pattern_id": 0,
                            "template_playlist_track": 4,
                        },
                        {
                            "source_input": 0,
                            "source_track_position": 2,
                            "source_channel": 9,
                            "template_channel_id": 1,
                            "template_pattern_id": 1,
                            "template_playlist_track": 5,
                        },
                    ],
                }
            }
        )
        replace_inventory(inspection, document, template.read_bytes())
        return arrangement, inspection, document, backend

    return make


def test_explicit_dry_run_preserves_full_provenance_and_converts_exactly(
    planning_case, monkeypatch
):
    arrangement, inspection, bindings, _ = planning_case()

    def unexpected(*args, **kwargs):
        pytest.fail("Pure planning invoked a process")

    monkeypatch.setattr("subprocess.run", unexpected)
    originals = [item.model_dump_json() for item in (arrangement, inspection, bindings)]
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "review_required" and not plan.execution_allowed
    assert plan.compatibility == "unverified" and plan.target_ppq == 96
    assert plan.tempo_millibpm == 120000
    assert [
        (p.notes[0].start_tick, p.notes[0].duration_ticks, p.clip_length_ticks) for p in plan.parts
    ] == [(24, 48, 72), (48, 24, 72)]
    assert [(p.notes[0].source_channel, p.binding.template_channel_id) for p in plan.parts] == [
        (2, 0),
        (9, 1),
    ]
    assert plan.unbound_sources == []
    assert (
        plan.arrangement == arrangement
        and plan.inspection == inspection
        and plan.bindings == bindings
    )
    assert DryRunBuildPlanner().plan(arrangement, inspection, bindings) == plan
    assert DryRunBuildPlan.model_validate_json(plan.model_dump_json()) == plan
    plan.arrangement.sources[0].midi.tracks[1].events[0].message["name"] = "changed"
    plan.inspection.project.channels[0]["name"] = "changed"
    plan.bindings.config.bindings[0].template_playlist_track = 10
    assert [item.model_dump_json() for item in (arrangement, inspection, bindings)] == originals


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"start": 121}, "ppq_inexact"),
        ({"duration": 0}, "note_range_unsupported"),
        ({"tempo": 500001}, "tempo_precision_unsupported"),
        ({"tempo": 10000}, "tempo_range_unsupported"),
        ({"meter": (3, 4)}, "meter_unsupported"),
        (
            {"changes": [mido.MetaMessage("set_tempo", tempo=600000, time=480)]},
            "tempo_map_unsupported",
        ),
        (
            {"changes": [mido.MetaMessage("time_signature", numerator=3, denominator=4, time=480)]},
            "meter_unsupported",
        ),
        ({"start": 0, "duration": 480 * 100000, "target_ppq": 32767}, "tick_range_unsupported"),
    ],
)
def test_unsupported_music_returns_blocked_plan_without_approximating(planning_case, kwargs, code):
    arrangement, inspection, bindings, _ = planning_case(**kwargs)
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked" and not plan.execution_allowed
    assert any(d.code == code and d.severity == "error" for d in plan.diagnostics)
    assert plan.arrangement == arrangement
    if code in {"ppq_inexact", "tick_range_unsupported", "note_range_unsupported"}:
        assert plan.parts[0].notes is None and plan.parts[0].clip_length_ticks is None


@pytest.mark.parametrize(
    "message",
    [
        mido.Message("control_change", channel=2, control=64, value=127),
        mido.Message("pitchwheel", channel=2, pitch=50),
        mido.Message("program_change", channel=2, program=5),
        mido.Message("sysex", data=[1, 2]),
    ],
)
def test_source_performance_events_are_not_silently_discarded(planning_case, message):
    arrangement, inspection, bindings, _ = planning_case(extra=[message])
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    event = next(d for d in plan.diagnostics if d.code == "source_event_unsupported")
    assert event.source_input == 0 and event.track_index == 1 and event.event_index == 1
    assert message.type in event.message and plan.status == "blocked"


def test_partial_binding_is_explicitly_blocked(planning_case):
    arrangement, inspection, bindings, _ = planning_case()
    bindings.config.bindings.pop()
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked" and len(plan.parts) == 1
    assert [
        (s.source_input, s.source_track_position, s.source_channel) for s in plan.unbound_sources
    ] == [(0, 2, 9)]


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_input", 99),
        ("source_track_position", 0),
        ("source_channel", 0),
        ("template_channel_id", 99),
        ("template_pattern_id", 99),
    ],
)
def test_unknown_source_or_target_ids_fail_without_guessing_names(planning_case, field, value):
    arrangement, inspection, bindings, _ = planning_case()
    setattr(bindings.config.bindings[0], field, value)
    with pytest.raises(BuildPlanningError):
        DryRunBuildPlanner().plan(arrangement, inspection, bindings)


@pytest.mark.parametrize(
    "fault",
    [
        "no_sources",
        "missing_options",
        "channel_changed",
        "origin_missing",
        "timing_changed",
        "binding_hash",
        "inspection_hash",
        "inspection_ppq",
        "unrecorded_roles",
    ],
)
def test_inconsistent_provenance_never_becomes_a_plan(planning_case, fault):
    arrangement, inspection, bindings, _ = planning_case()
    if fault == "no_sources":
        arrangement.sources = []
    elif fault == "missing_options":
        arrangement.build_options = None
    elif fault == "channel_changed":
        arrangement.tracks[1].notes[0].channel = 4
    elif fault == "origin_missing":
        arrangement.tracks[1].note_origins = []
    elif fault == "timing_changed":
        arrangement.tracks[1].notes[0].start_tick = 999
    elif fault == "binding_hash":
        bindings.config.template_sha256 = "0" * 64
    elif fault == "inspection_hash":
        inspection.template_sha256_after = "0" * 64
    elif fault == "inspection_ppq":
        inspection.project.ppq = 480
    elif fault == "unrecorded_roles":
        arrangement.tracks[1].instrument_roles.append(
            InstrumentAssignment(source_channel=2, role="invented", rule_index=0)
        )
    with pytest.raises(BuildPlanningError):
        DryRunBuildPlanner().plan(arrangement, inspection, bindings)


@pytest.mark.parametrize(
    "fault,code",
    [
        ("no_playlist", "playlist_event_unverified"),
        ("empty_pattern", "pattern_note_event_unverified"),
        ("version", "template_version_unsupported"),
        ("automation", "channel_capability_unsupported"),
        ("sequenced", "channel_capability_unsupported"),
    ],
)
def test_template_capability_limits_block_preview_eligibility(planning_case, fault, code):
    arrangement, inspection, bindings, _ = planning_case()
    if fault == "no_playlist":
        inspection.project.playlist_item_count = 0
    elif fault == "empty_pattern":
        inspection.project.patterns[0]["noteCount"] = 0
    elif fault == "version":
        inspection.project.fl_studio_version = "99.0.0.1"
    elif fault == "automation":
        inspection.project.channels[0]["generator"] = "Automation"
    elif fault == "sequenced":
        inspection.project.channels[0]["isLikelySequenced"] = True
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked" and any(d.code == code for d in plan.diagnostics)


@pytest.mark.parametrize(
    "target",
    ["source_channel", "template_channel_id", "template_pattern_id", "template_playlist_track"],
)
def test_binding_schema_rejects_collisions_and_implicit_channel_merges(planning_case, target):
    _, _, bindings, _ = planning_case()
    raw = bindings.model_dump()
    if target == "source_channel":
        raw["config"]["bindings"][1].update(
            {
                k: raw["config"]["bindings"][0][k]
                for k in ("source_input", "source_track_position", "source_channel")
            }
        )
    else:
        raw["config"]["bindings"][1][target] = raw["config"]["bindings"][0][target]
    with pytest.raises(ValidationError):
        TemplateBindingDocument.model_validate(raw)


def test_binding_loader_retains_exact_bytes_and_rejects_duplicate_yaml(tmp_path, planning_case):
    _, _, bindings, _ = planning_case()
    path = tmp_path / "bindings.yaml"
    raw = json.dumps(bindings.config.model_dump()).encode()
    path.write_bytes(raw)
    document = load_template_bindings(path)
    assert (
        document.config == bindings.config
        and document.source_sha256 == hashlib.sha256(raw).hexdigest()
    )
    assert document.source_path == path.resolve()
    path.write_text("bindings: []\nbindings: []")
    with pytest.raises(ConfigurationError):
        load_template_bindings(path)


def test_recorded_roles_and_cleanup_audits_are_independent_snapshots(planning_case):
    from suno2flp.core.config import MidiPreferences
    from suno2flp.core.models import ArrangementOptions
    from suno2flp.midi_processor import DeterministicMidiProcessor

    arrangement, inspection, bindings, _ = planning_case(start=121, target_ppq=960)
    cleaned = DeterministicMidiProcessor().clean(
        arrangement.sources[0].midi, MidiPreferences(quantize=True, quantize_grid_ticks=120)
    )
    arrangement = FaithfulArrangementEngine().arrange(
        [cleaned], MusicalMetadata(), "faithful", options=ArrangementOptions(note_view="active")
    )
    mapping = InstrumentMappingDocument.model_validate(
        {
            "config": {
                "roles": {"piano": {}},
                "mappings": [
                    {
                        "source_input": 0,
                        "source_track_position": 1,
                        "source_channel": 2,
                        "role": "piano",
                    }
                ],
            }
        }
    )
    mapped = ExplicitInstrumentMapper().apply(arrangement, mapping)
    plan = DryRunBuildPlanner().plan(mapped, inspection, bindings)
    assert (
        plan.status == "review_required"
        and plan.arrangement.instrument_mapping == mapped.instrument_mapping
    )
    assert plan.arrangement.sources[0].midi.cleanup == cleaned.cleanup
    assert plan.parts[0].notes[0].start_tick == 240


def test_cli_plan_is_read_only_and_blocked_plans_are_reviewable(
    planning_case, tmp_path, monkeypatch
):
    arrangement, inspection, bindings, backend = planning_case()
    paths = [tmp_path / name for name in ("arrangement.json", "inspection.json", "bindings.yaml")]
    for path, model in zip(paths, (arrangement, inspection, bindings.config), strict=True):
        path.write_text(model.model_dump_json())
    before = {p: p.read_bytes() for p in [*paths, inspection.template_path]}

    def unexpected(*args, **kwargs):
        pytest.fail("plan-build invoked a process")

    monkeypatch.setattr("subprocess.run", unexpected)
    args = [
        "plan-build",
        str(paths[0]),
        "--inspection",
        str(paths[1]),
        "--bindings",
        str(paths[2]),
        "--backend-dir",
        str(backend),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    plan = json.loads(result.stdout)
    assert plan["status"] == "review_required" and plan["execution_allowed"] is False
    assert len(plan["input_files"]) == 3
    assert {f["kind"]: f["sha256"] for f in plan["input_files"]} == {
        kind: hashlib.sha256(path.read_bytes()).hexdigest()
        for kind, path in zip(("arrangement", "inspection", "bindings"), paths, strict=True)
    }
    output = tmp_path / "plan.json"
    assert CliRunner().invoke(app, [*args, "--output", str(output)]).exit_code == 0
    saved = output.read_bytes()
    assert CliRunner().invoke(app, [*args, "--output", str(output)]).exit_code == 1
    assert output.read_bytes() == saved
    assert CliRunner().invoke(app, [*args, "--output", str(backend / "never.json")]).exit_code == 1
    assert not (backend / "never.json").exists()
    assert (
        CliRunner()
        .invoke(app, [*args, "--output", str(inspection.template_path) + ":plan.json"])
        .exit_code
        == 1
    )
    assert before == {p: p.read_bytes() for p in before}
    bindings.config.bindings.pop()
    paths[2].write_text(bindings.config.model_dump_json())
    blocked = tmp_path / "blocked.json"
    assert CliRunner().invoke(app, [*args, "--output", str(blocked)]).exit_code == 1
    assert json.loads(blocked.read_text())["status"] == "blocked"
    inspection.template_path.write_bytes(b"changed template")
    absent = tmp_path / "must-not-exist.json"
    result = CliRunner().invoke(app, [*args, "--output", str(absent)])
    assert result.exit_code == 1 and not absent.exists()


def test_multichannel_source_uses_distinct_explicit_template_targets(planning_case):
    arrangement, inspection, bindings, _ = planning_case(multichannel=True)
    bindings.config.bindings[1].source_track_position = 1
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "review_required"
    assert [p.arrangement_track_index for p in plan.parts] == [1, 1]
    assert [(p.notes[0].source_channel, p.notes[0].arrangement_note_index) for p in plan.parts] == [
        (2, 0),
        (9, 1),
    ]
    assert [n.channel for n in plan.arrangement.tracks[1].notes] == [2, 9]


def test_multiple_inputs_keep_exact_source_identities_despite_repeated_names(planning_case):
    arrangement, inspection, bindings, _ = planning_case()
    source = arrangement.sources[0].midi
    combined = FaithfulArrangementEngine().arrange([source, source], MusicalMetadata(), "faithful")
    raw = bindings.model_dump()
    for index, old in enumerate(list(raw["config"]["bindings"])):
        new = {
            **old,
            "source_input": 1,
            "template_channel_id": index + 2,
            "template_pattern_id": index + 2,
            "template_playlist_track": index + 6,
        }
        raw["config"]["bindings"].append(new)
        inspection.project.channels.append(
            {
                "id": index + 2,
                "name": "Same name",
                "generator": "Sampler",
                "isLikelySequenced": False,
            }
        )
        inspection.project.patterns.append({"id": index + 2, "name": "Same name", "noteCount": 1})
    inspection.header.channel_count = 4
    inspection.project.playlist_item_count = 4
    expanded_bindings = TemplateBindingDocument.model_validate(raw)
    replace_inventory(inspection, expanded_bindings, template_bytes(slots=4))
    plan = DryRunBuildPlanner().plan(combined, inspection, expanded_bindings)
    assert plan.status == "review_required"
    assert [(p.binding.source_input, p.arrangement_track_index) for p in plan.parts] == [
        (0, 1),
        (0, 2),
        (1, 4),
        (1, 5),
    ]


def test_old_summary_only_inspection_requires_refresh(planning_case):
    arrangement, inspection, bindings, _ = planning_case()
    inspection.inventory = None
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked"
    assert any(d.code == "template_inventory_missing" for d in plan.diagnostics)


@pytest.mark.parametrize(
    "fault,code",
    [
        ("crop", "template_crop_unsupported"),
        ("muted", "template_muted_clip_unsupported"),
        ("unbound_notes", "template_notes_unbound"),
        ("automation", "template_automation_unsupported"),
        ("repeated_notes", "template_note_events_ambiguous"),
        ("repeated_playlist", "template_playlist_events_ambiguous"),
        ("no_fine_tempo", "template_tempo_event_unverified"),
        ("opaque", "template_inventory_incomplete"),
    ],
)
def test_inventory_hazards_block_without_discarding_provenance(planning_case, fault, code):
    arrangement, inspection, bindings, _ = planning_case()
    options = (
        {"crop": 0.125}
        if fault == "crop"
        else {"muted": True}
        if fault == "muted"
        else {"other_notes": True}
        if fault == "unbound_notes"
        else {}
    )
    extra = {
        "automation": b"\xdf\x06legacy",
        "repeated_notes": b"\x41\x01\0\xe0\0",
        "repeated_playlist": b"\xe9\0",
        "opaque": b"\xfa\x03new",
    }.get(fault, b"")
    raw = template_bytes(extra=extra, **options)
    if fault == "no_fine_tempo":
        raw = raw.replace(b"\x9c\xc0\xd4\x01\0", b"")
        raw = raw[:18] + struct.pack("<I", len(raw) - 22) + raw[22:]
    replace_inventory(inspection, bindings, raw)
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked" and any(d.code == code for d in plan.diagnostics)
    assert plan.inspection.inventory == inspection.inventory
    assert plan.arrangement == arrangement and not plan.execution_allowed


def test_plans_link_notes_and_clips_to_inventory_and_hash_snapshot(planning_case):
    from suno2flp.flp_builder.planning import snapshot_sha256

    arrangement, inspection, bindings, _ = planning_case()
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.algorithm_version == 2 and plan.capability_profile.endswith("-v2")
    assert plan.inventory_snapshot_sha256 == snapshot_sha256(inspection.inventory)
    assert [p.template_note_indices for p in plan.parts] == [[0], [1]]
    assert [p.template_clip_indices for p in plan.parts] == [[0], [1]]


def test_file_planning_rejects_modified_inventory_with_unchanged_template(planning_case, tmp_path):
    from suno2flp.flp_builder.planning_files import plan_build_files

    arrangement, inspection, bindings, backend = planning_case()
    # A structurally valid but false event hash in a metadata event.
    inspection.inventory.events[0].payload_sha256 = "0" * 64
    paths = [tmp_path / name for name in ("arrangement.json", "inspection.json", "bindings.yaml")]
    for path, model in zip(paths, (arrangement, inspection, bindings.config), strict=True):
        path.write_text(model.model_dump_json())
    with pytest.raises(BuildPlanningError, match="template_inventory_stale"):
        plan_build_files(*paths, backend)


@pytest.mark.parametrize(
    "extra,code",
    [
        (b"\x40\0\0\0\0", "template_channel_disabled"),
        (b"\x11\x03\x12\x04", "template_meter_conflict"),
        (b"\x42\x78\0", "template_tempo_conflict"),
        (b"\x63\0\0", "template_arrangements_unsupported"),
        (b"\x9c\xc0\xd4\x01\0", "template_tempo_event_unverified"),
    ],
)
def test_inherited_channel_meter_and_arrangement_state_is_not_inferred_safe(
    planning_case, extra, code
):
    arrangement, inspection, bindings, _ = planning_case()
    replace_inventory(inspection, bindings, template_bytes(extra=extra))
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked" and any(item.code == code for item in plan.diagnostics)


@pytest.mark.parametrize("fault", ["clips", "notes", "version"])
def test_inventory_summary_disagreement_is_blocking_evidence(planning_case, fault):
    arrangement, inspection, bindings, _ = planning_case()
    if fault == "clips":
        inspection.project.playlist_item_count += 1
    elif fault == "notes":
        inspection.project.patterns[0]["noteCount"] += 1
    else:
        inspection.project.fl_studio_version = "other"
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert any(
        d.code == "template_inventory_summary_mismatch" and d.severity == "error"
        for d in plan.diagnostics
    )


def test_wrong_template_lane_and_note_attributes_block_inheritance(planning_case):
    arrangement, inspection, bindings, _ = planning_case()
    raw = bytearray(template_bytes())
    first_note = inspection.inventory.notes[0].file_offset
    raw[first_note + 4] = 1
    first_clip = inspection.inventory.clips[0].file_offset
    struct.pack_into("<H", raw, first_clip + 12, 499 - 10)
    replace_inventory(inspection, bindings, bytes(raw))
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    codes = {d.code for d in plan.diagnostics}
    assert {"template_note_attributes_unsupported", "template_clip_binding_conflict"} <= codes
    assert not plan.parts[0].template_clip_indices


@pytest.mark.parametrize(
    "fault,code",
    [
        ("overflow", "template_pattern_index_overflow"),
        ("mixed_bases", "template_pattern_base_ambiguous"),
    ],
)
def test_playlist_encoding_base_is_checked_with_every_planned_pattern(planning_case, fault, code):
    arrangement, inspection, bindings, _ = planning_case()
    raw = bytearray(template_bytes())
    if fault == "overflow":
        # Both original clips reference Pattern 0 and are individually representable;
        # the second planned target would encode as 65536, beyond the ushort field.
        for item in inspection.inventory.clips:
            struct.pack_into("<HH", raw, item.file_offset + 4, 65534, 65535)
            struct.pack_into("<H", raw, item.file_offset + 12, 499 - 4)
    else:
        second = inspection.inventory.clips[1]
        struct.pack_into("<HH", raw, second.file_offset + 4, 3, 5)
    replace_inventory(inspection, bindings, bytes(raw))
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked" and any(d.code == code for d in plan.diagnostics)
    assert len(plan.parts) == 2 and plan.parts[1].notes[0].source_channel == 9


def test_fl26_inventory_never_enables_the_fl25_writer_capability_profile(planning_case):
    from suno2flp.core.template_summary import compare_backend_summary

    arrangement, inspection, bindings, _ = planning_case()
    replace_inventory(inspection, bindings, template_bytes(version="26.1.7.5654", stride=88))
    inspection.project.fl_studio_version = "26.1.7.5654"
    local, status, mismatches = compare_backend_summary(inspection.inventory, inspection.project)
    inspection.local_summary = local
    inspection.backend_summary_status = status
    inspection.backend_summary_mismatches = mismatches
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert status == "consistent" and plan.status == "blocked"
    assert any(d.code == "template_read_only_profile" for d in plan.diagnostics)
    assert plan.inspection == inspection and not plan.execution_allowed


@pytest.mark.parametrize("fault", ["local", "status", "mismatches"])
def test_planning_checks_recorded_comparison_provenance(planning_case, fault):
    from suno2flp.core.template_summary import compare_backend_summary

    arrangement, inspection, bindings, _ = planning_case()
    local, status, mismatches = compare_backend_summary(inspection.inventory, inspection.project)
    inspection.local_summary = local
    inspection.backend_summary_status = status
    inspection.backend_summary_mismatches = mismatches
    if fault == "local":
        inspection.local_summary.tempo_millibpm = 130000
    elif fault == "status":
        inspection.backend_summary_status = "inconsistent"
    else:
        inspection.project.patterns[0]["noteCount"] += 1
    with pytest.raises(BuildPlanningError, match="inspection_inconsistent"):
        DryRunBuildPlanner().plan(arrangement, inspection, bindings)


@pytest.mark.parametrize(
    "patch",
    [
        {"source_channel": True},
        {"source_input": 1.0},
        {"source_track_position": -1},
        {"template_channel_id": 256},
        {"template_pattern_id": -1},
        {"template_playlist_track": 500},
        {"track_name": "Same name"},
        {"role": "piano"},
    ],
)
def test_binding_selectors_are_strict_and_have_no_name_or_role_fallback(planning_case, patch):
    _, _, bindings, _ = planning_case()
    raw = bindings.model_dump()
    raw["config"]["bindings"][0].update(patch)
    with pytest.raises(ValidationError):
        TemplateBindingDocument.model_validate(raw)


def test_cli_refuses_changed_backend_before_creating_plan(planning_case, tmp_path):
    arrangement, inspection, bindings, backend = planning_case()
    paths = [tmp_path / name for name in ("arrangement.json", "inspection.json", "bindings.yaml")]
    for path, model in zip(paths, (arrangement, inspection, bindings.config), strict=True):
        path.write_text(model.model_dump_json())
    (backend / "publish/music2daw.dll").write_bytes(b"changed")
    output = tmp_path / "never.json"
    result = CliRunner().invoke(
        app,
        [
            "plan-build",
            str(paths[0]),
            "--inspection",
            str(paths[1]),
            "--bindings",
            str(paths[2]),
            "--backend-dir",
            str(backend),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1 and "backend_integrity_failed" in result.output
    assert not output.exists()
