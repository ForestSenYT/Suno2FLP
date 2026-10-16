"""Original synthetic writer fixtures; no private FLP or host-compatibility claims."""

import hashlib
import json
import os
import struct
from pathlib import Path

import pytest
from test_build_planning import planning_case as planning_case
from test_build_planning import replace_inventory
from test_fl26_inventory import event, project

from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.template_summary import compare_backend_summary
from suno2flp.integrations.template_inventory import scan_template_inventory


def original_fixture():
    events = event(199, b"26.1.7.5654\0") + event(172, b"\x01\x01\0")
    events += event(156, struct.pack("<I", 120000)) + event(17, b"\x04") + event(18, b"\x04")
    clips = []
    for index in range(2):
        events += event(64, struct.pack("<H", index)) + event(0, b"\x01") + event(21, b"\x02")
        events += event(201, (f"FixtureSynth{index}\0").encode("utf-16-le"))
        events += event(212, b"original initialization") + event(
            213, b"original opaque plugin state"
        )
        note = bytearray(24)
        struct.pack_into("<i", note, 0, 96)
        struct.pack_into("<i", note, 8, 48)
        note[6], note[12], note[20], note[21] = index, 60, 64, 80
        events += event(65, struct.pack("<H", index + 1)) + event(224, note)
        clip = bytearray(88)
        struct.pack_into("<iHHiHH", clip, 0, 0, 2, index + 3, 192, 495 - index, 0)
        clip[80:] = bytes(range(index + 1, index + 9))
        clips.append(clip)
    events += event(233, b"".join(clips))
    raw = bytearray(project(events))
    struct.pack_into("<H", raw, 10, 2)
    return bytes(raw)


def policy_for(inspection, bindings):
    from suno2flp.core.writer_models import Fl26WriterPolicy, WriterPolicyDocument

    inventory = inspection.inventory
    generators = [e for e in inventory.events if e.event_id == 201]
    return WriterPolicyDocument(
        config=Fl26WriterPolicy.model_validate(
            {
                "schema_version": 1,
                "profile": "fl26-26.1.7.5654-write-v1",
                "template_sha256": inspection.template_sha256_after,
                "inventory_snapshot_sha256": snapshot_sha256(inventory),
                "bindings_snapshot_sha256": snapshot_sha256(bindings.config),
                "reference_kind": "synthetic_fixture",
                "reviewer": "original fixture test",
                "reference_evidence": "Original synthetic structure only; no host playback check",
                "dependency_review": "attested",
                "instrument_review": "attested",
                "local_use_review": "attested",
                "content_policy": "replace_all_bound_notes_and_clips",
                "note_attribute_policy": "preserve_reviewed_prototype",
                "clip_extension_policy": "preserve_exact_reference_bytes",
                "targets": [
                    {
                        "binding_index": i,
                        "note_index": i,
                        "clip_index": i,
                        "note_sha256": hashlib.sha256(
                            bytes.fromhex(inventory.notes[i].raw_hex)
                        ).hexdigest(),
                        "clip_sha256": hashlib.sha256(
                            bytes.fromhex(inventory.clips[i].raw_hex)
                        ).hexdigest(),
                        "generator_event_index": generators[i].event_index,
                        "generator_name": f"FixtureSynth{i}",
                    }
                    for i in range(2)
                ],
            }
        )
    )


@pytest.fixture
def writer_case(planning_case):
    def make(**options):
        arrangement, inspection, bindings, backend = planning_case(**options)
        raw = original_fixture()
        replace_inventory(inspection, bindings, raw)
        inspection.project.fl_studio_version = "26.1.7.5654"
        for i, channel in enumerate(inspection.project.channels):
            channel["generator"] = f"FixtureSynth{i}"
        local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
        (
            inspection.local_summary,
            inspection.backend_summary_status,
            inspection.backend_summary_mismatches,
        ) = local, status, mismatch
        return arrangement, inspection, bindings, policy_for(inspection, bindings), backend

    return make


def intent_for(case):
    from suno2flp.flp_builder.writer_intent import prepare_fl26_write

    arrangement, inspection, bindings, policy, _ = case
    return prepare_fl26_write(
        inspection.template_path.read_bytes(), arrangement, inspection, bindings, policy
    )


def test_ready_intent_preserves_complete_snapshots_and_exact_coordinates(writer_case):
    case = writer_case()
    before = [x.model_dump_json() for x in case[:4]]
    intent = intent_for(case)
    assert intent.status == "ready" and intent.compatibility == "unverified"
    assert intent.reference_kind == "synthetic_fixture"
    assert [p.notes[0].source_channel for p in intent.binding_check.parts] == [2, 9]
    assert (
        intent.binding_check.parts[0].notes[0].start_tick,
        intent.binding_check.parts[0].notes[0].duration_ticks,
    ) == (24, 48)
    assert (
        intent.arrangement == case[0] and intent.inspection == case[1] and intent.policy == case[3]
    )
    assert before == [x.model_dump_json() for x in case[:4]]


@pytest.mark.parametrize(
    "fault,code",
    [
        ("zero_length", "writer_note_range"),
        ("note_flags", "writer_note_attributes"),
        ("crop", "writer_crop"),
        ("negative_zero_crop", "writer_crop"),
        ("clip_flags", "writer_clip_attributes"),
        ("unknown_event", "writer_event_unsupported"),
        ("automation", "writer_automation"),
        ("disabled", "writer_channel_unverified"),
        ("generator", "writer_generator_unverified"),
        ("backend", "writer_backend_inconsistent"),
        ("policy_identity", "writer_policy_stale"),
        ("prototype_hash", "writer_prototype_unverified"),
        ("unbound", "source_bindings_incomplete"),
    ],
)
def test_unresolved_evidence_blocks_without_force_or_guessing(writer_case, fault, code):
    case = writer_case()
    arrangement, inspection, bindings, policy, backend = case
    raw = bytearray(inspection.template_path.read_bytes())
    n, c = inspection.inventory.notes[0], inspection.inventory.clips[0]
    if fault == "zero_length":
        raw[n.file_offset + 8 : n.file_offset + 12] = b"\0" * 4
    elif fault == "note_flags":
        raw[n.file_offset + 4 : n.file_offset + 6] = b"\0\x40"
    elif fault in {"crop", "negative_zero_crop"}:
        raw[c.file_offset + 24 : c.file_offset + 28] = (
            b"\xff" * 4 if fault == "crop" else b"\0\0\0\x80"
        )
    elif fault == "clip_flags":
        raw[c.file_offset + 18 : c.file_offset + 20] = b"\0\x20"
    elif fault == "disabled":
        e = next(e for e in inspection.inventory.events if e.event_id == 0)
        raw[e.payload_offset] = 0
    elif fault == "generator":
        e = next(e for e in inspection.inventory.events if e.event_id == 201)
        raw[e.payload_offset : e.payload_offset + e.payload_size] = b"\0" * e.payload_size
    elif fault in {"unknown_event", "automation"}:
        extra = event(250 if fault == "unknown_event" else 223, b"opaque")
        raw.extend(extra)
        struct.pack_into("<I", raw, 18, len(raw) - 22)
    if raw != inspection.template_path.read_bytes():
        replace_inventory(inspection, bindings, bytes(raw))
        local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
        (
            inspection.local_summary,
            inspection.backend_summary_status,
            inspection.backend_summary_mismatches,
        ) = local, status, mismatch
        policy = policy_for(inspection, bindings)
    if fault == "backend":
        inspection.project.patterns = []
        local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
        (
            inspection.local_summary,
            inspection.backend_summary_status,
            inspection.backend_summary_mismatches,
        ) = local, status, mismatch
    elif fault == "policy_identity":
        policy.config.template_sha256 = "0" * 64
    elif fault == "prototype_hash":
        policy.config.targets[0].note_sha256 = "0" * 64
    elif fault == "unbound":
        bindings.config.bindings.pop()
        policy = policy_for(inspection, bindings)
        policy.config.targets.pop()
    intent = intent_for((arrangement, inspection, bindings, policy, backend))
    assert intent.status == "blocked"
    assert code in {d.code for d in intent.diagnostics}


@pytest.mark.parametrize(
    "options,code",
    [
        ({"start": 1}, "ppq_inexact"),
        ({"duration": 1}, "ppq_inexact"),
        ({"meter": (3, 4)}, "writer_meter"),
        ({"tempo": 500001}, "writer_tempo_precision"),
    ],
)
def test_unsupported_timing_is_blocked_exactly(writer_case, options, code):
    intent = intent_for(writer_case(**options))
    assert intent.status == "blocked" and code in {d.code for d in intent.diagnostics}


def test_source_controls_are_not_silently_discarded(writer_case):
    import mido

    intent = intent_for(
        writer_case(extra=[mido.Message("control_change", channel=2, control=64, value=127)])
    )
    assert intent.status == "blocked" and "source_event_unsupported" in {
        d.code for d in intent.diagnostics
    }


def test_encoder_and_independent_verifier_preserve_non_targets_and_full_clip_tails(writer_case):
    from suno2flp.flp_builder.fl26_codec import encode_fl26
    from suno2flp.flp_builder.fl26_verify import verify_fl26_output

    case = writer_case()
    raw = case[1].template_path.read_bytes()
    intent = intent_for(case)
    encoded = encode_fl26(raw, intent)
    proof = verify_fl26_output(raw, encoded, intent)
    decoded = scan_template_inventory(encoded)
    assert proof.output_sha256 == hashlib.sha256(encoded).hexdigest()
    assert proof.note_count == 2 and proof.clip_count == 2
    assert [(n.position_ticks, n.length_ticks, n.channel_id) for n in decoded.notes] == [
        (24, 48, 0),
        (48, 24, 1),
    ]
    assert [c.extension_hex for c in decoded.clips] == [
        c.extension_hex for c in intent.inspection.inventory.clips
    ]
    assert decoded.events[1].event_id == 172 and decoded.events[1].scalar_hex == "010100"
    allowed = {e.event_index for e in decoded.events if e.event_id in {156, 224, 233}}
    assert set(proof.changed_event_indices) <= allowed
    for index, old in enumerate(intent.inspection.inventory.events):
        if index not in proof.changed_event_indices:
            new = decoded.events[index]
            assert (
                raw[old.file_offset : old.payload_offset + old.payload_size]
                == encoded[new.file_offset : new.payload_offset + new.payload_size]
            )
    assert case[1].template_path.read_bytes() == raw


def test_multibyte_note_lengths_and_resized_offsets_are_verified(writer_case):
    import mido

    from suno2flp.arrangement import FaithfulArrangementEngine
    from suno2flp.flp_builder.fl26_codec import encode_fl26
    from suno2flp.flp_builder.fl26_verify import verify_fl26_output
    from suno2flp.importer import MidiFileImporter

    case = writer_case()
    arrangement, inspection, bindings, policy, backend = case
    midi = mido.MidiFile(arrangement.sources[0].midi.source)
    for _ in range(10):
        midi.tracks[1].insert(
            -1, mido.Message("note_on", channel=2, note=62, velocity=70, time=120)
        )
        midi.tracks[1].insert(-1, mido.Message("note_off", channel=2, note=62, time=120))
    midi.save(arrangement.sources[0].midi.source)
    arrangement = FaithfulArrangementEngine().arrange(
        [MidiFileImporter().import_file(arrangement.sources[0].midi.source)],
        arrangement.metadata,
        "faithful",
    )
    intent = intent_for((arrangement, inspection, bindings, policy, backend))
    raw = inspection.template_path.read_bytes()
    out = encode_fl26(raw, intent)
    proof = verify_fl26_output(raw, out, intent)
    assert proof.note_count == 12 and len(out) > len(raw)
    assert any(
        e.payload_size > 127 and len(bytes.fromhex(e.header_hex)) > 2
        for e in scan_template_inventory(out).events
        if e.event_id == 224
    )


@pytest.mark.parametrize(
    "fault", ["note", "clip_extension", "tempo", "plugin", "truncated", "extra_note"]
)
def test_independent_verifier_rejects_mutated_output(writer_case, fault):
    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder.fl26_codec import encode_fl26
    from suno2flp.flp_builder.fl26_verify import verify_fl26_output

    case = writer_case()
    raw, intent = case[1].template_path.read_bytes(), intent_for(case)
    encoded = bytearray(encode_fl26(raw, intent))
    inventory = scan_template_inventory(bytes(encoded))
    if fault == "note":
        encoded[inventory.notes[0].file_offset + 12] ^= 1
    elif fault == "clip_extension":
        encoded[inventory.clips[0].file_offset + 80] ^= 1
    elif fault in {"tempo", "plugin"}:
        e = next(e for e in inventory.events if e.event_id == (156 if fault == "tempo" else 213))
        encoded[e.payload_offset] ^= 1
    elif fault == "truncated":
        encoded.pop()
    else:
        e = next(e for e in inventory.events if e.event_id == 224)
        payload = encoded[e.payload_offset : e.payload_offset + e.payload_size]
        replacement = event(224, payload + payload)
        encoded[e.file_offset : e.payload_offset + e.payload_size] = replacement
        struct.pack_into("<I", encoded, 18, len(encoded) - 22)
    with pytest.raises(FlpWriteError):
        verify_fl26_output(raw, bytes(encoded), intent)


def test_forged_ready_intent_cannot_bypass_reconstruction(writer_case):
    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder.fl26_codec import encode_fl26

    case = writer_case()
    intent = intent_for(case)
    intent.binding_check.parts[0].notes[0].start_tick += 1
    with pytest.raises(FlpWriteError, match="intent"):
        encode_fl26(case[1].template_path.read_bytes(), intent)


def save_case(tmp_path, case):
    a, i, b, p = [
        tmp_path / name
        for name in ("arrangement.json", "inspection.json", "bindings.yaml", "policy.yaml")
    ]
    for path, model in zip(
        (a, i, b, p), (case[0], case[1], case[2].config, case[3].config), strict=True
    ):
        path.write_text(model.model_dump_json(), encoding="utf-8")
    return a, i, b, p, case[4]


@pytest.mark.skipif(os.name != "nt", reason="No-replace bundle publication is Windows-only")
def test_file_build_publishes_complete_new_bundle_and_preserves_every_input(
    tmp_path, writer_case, monkeypatch
):
    from suno2flp.flp_builder.writer_files import build_fl26_files

    case = writer_case()
    a, i, b, p, backend = save_case(tmp_path, case)
    destination = tmp_path.parent / (tmp_path.name + "-bundle")
    original = case[1].template_path.read_bytes(), case[1].template_path.stat().st_mtime_ns
    monkeypatch.setattr(
        "subprocess.run", lambda *_a, **_k: pytest.fail("Writer launched a process")
    )
    result = build_fl26_files(a, i, b, p, backend, destination)
    assert result.output_path == destination / "project.flp"
    assert {x.name for x in destination.iterdir()} == {
        "project.flp",
        "provenance.json",
        "verification.json",
    }
    provenance = json.loads((destination / "provenance.json").read_text())
    assert provenance["intent"]["arrangement"] == json.loads(case[0].model_dump_json())
    assert provenance["intent"]["reference_kind"] == "synthetic_fixture"
    assert provenance["compatibility"] == "unverified"
    for f in provenance["input_files"]:
        assert hashlib.sha256(Path(f["path"]).read_bytes()).hexdigest() == f["sha256"]
    assert (
        case[1].template_path.read_bytes(),
        case[1].template_path.stat().st_mtime_ns,
    ) == original
    assert "host_compatibility_unverified" in {d.code for d in result.diagnostics}


@pytest.mark.parametrize(
    "fault", ["existing", "input_tree", "backend_tree", "ads", "device", "media_suffix"]
)
def test_unsafe_output_is_refused_before_staging(tmp_path, writer_case, fault):
    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder.writer_files import build_fl26_files

    case = writer_case()
    inputs = save_case(tmp_path, case)
    destination = tmp_path.parent / (tmp_path.name + "-bundle")
    if fault == "existing":
        destination.mkdir()
    elif fault == "input_tree":
        destination = tmp_path / "new-bundle"
    elif fault == "backend_tree":
        destination = case[4] / "new-bundle"
    elif fault == "ads":
        destination = Path(str(destination) + ":hidden")
    elif fault == "device":
        destination = tmp_path.parent / "CON"
    elif fault == "media_suffix":
        destination = tmp_path.parent / "new.flp"
    with pytest.raises(FlpWriteError):
        build_fl26_files(*inputs, destination)
    assert not list(tmp_path.parent.glob(".suno2flp-stage-*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows publication failure paths")
@pytest.mark.parametrize(
    "fault", ["encode", "verify", "sidecar", "race", "source_changed", "published_corrupt"]
)
def test_failures_do_not_overwrite_or_return_success(tmp_path, writer_case, monkeypatch, fault):
    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder import writer_files

    case = writer_case()
    inputs = save_case(tmp_path, case)
    destination = tmp_path.parent / (tmp_path.name + "-bundle")
    original = case[1].template_path.read_bytes()
    if fault in {"encode", "verify"}:

        def fail(*_a, **_k):
            raise RuntimeError("injected failure")

        monkeypatch.setattr(
            writer_files, "encode_fl26" if fault == "encode" else "verify_fl26_output", fail
        )
    elif fault == "sidecar":
        original_write = writer_files.write_new

        def fail(path, data):
            if path.name == "provenance.json":
                raise OSError("injected sidecar failure")
            original_write(path, data)

        monkeypatch.setattr(writer_files, "write_new", fail)
    else:
        original_publish = writer_files.publish_bundle

        def publish(stage, dest):
            if fault == "race":
                dest.mkdir()
                (dest / "keep.txt").write_text("untouched")
            elif fault == "source_changed":
                # Only the synthetic MIDI is changed, never a user FLP.
                source = case[0].sources[0].midi.source
                source.write_bytes(source.read_bytes() + b"x")
            original_publish(stage, dest)
            if fault == "published_corrupt":
                (dest / "project.flp").write_bytes(b"bad output")

        monkeypatch.setattr(writer_files, "publish_bundle", publish)
    with pytest.raises(FlpWriteError):
        writer_files.build_fl26_files(*inputs, destination)
    assert case[1].template_path.read_bytes() == original
    if fault == "race":
        assert (destination / "keep.txt").read_text() == "untouched"
    elif fault not in {"published_corrupt", "source_changed"}:
        assert not destination.exists()


@pytest.mark.parametrize("changed", ["midi", "policy", "backend", "snapshot"])
def test_file_preflight_rejects_stale_evidence_without_output(tmp_path, writer_case, changed):
    from suno2flp.core.errors import Suno2FLPError
    from suno2flp.flp_builder.writer_files import plan_fl26_files

    case = writer_case()
    a, i, b, p, backend = save_case(tmp_path, case)
    if changed == "midi":
        case[0].sources[0].midi.source.write_bytes(b"changed source")
    elif changed == "policy":
        data = json.loads(p.read_text())
        data["template_sha256"] = "0" * 64
        p.write_text(json.dumps(data))
    elif changed == "backend":
        (backend / "publish/music2daw.dll").write_bytes(b"changed backend")
    else:
        data = json.loads(a.read_text())
        data["sources"][0]["midi"]["tracks"][1]["events"][0]["message"]["name"] = "forged"
        a.write_text(json.dumps(data))
    if changed == "policy":
        assert plan_fl26_files(a, i, b, p, backend).intent.status == "blocked"
    else:
        with pytest.raises((Suno2FLPError, ValueError)):
            plan_fl26_files(a, i, b, p, backend)


def test_cli_writes_reviewable_intent_and_exclusive_build(tmp_path, writer_case):
    from typer.testing import CliRunner

    from suno2flp.cli import app

    case = writer_case()
    a, i, b, p, backend = save_case(tmp_path, case)
    args = [
        str(a),
        "--inspection",
        str(i),
        "--bindings",
        str(b),
        "--policy",
        str(p),
        "--backend-dir",
        str(backend),
    ]
    result = CliRunner().invoke(app, ["plan-flp-write", *args])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["intent"]["status"] == "ready"
    if os.name == "nt":
        out = tmp_path.parent / (tmp_path.name + "-cli-bundle")
        built = CliRunner().invoke(app, ["build-flp", *args, "--output-dir", str(out)])
        assert built.exit_code == 0, built.output
        assert (out / "project.flp").exists()


def test_independent_verifier_rejects_noncanonical_changed_length_prefix(writer_case):
    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder.fl26_codec import encode_fl26
    from suno2flp.flp_builder.fl26_verify import verify_fl26_output

    case = writer_case()
    raw, intent = case[1].template_path.read_bytes(), intent_for(case)
    encoded = bytearray(encode_fl26(raw, intent))
    inventory = scan_template_inventory(bytes(encoded))
    e = next(e for e in inventory.events if e.event_id == 224)
    encoded[e.file_offset : e.payload_offset] = bytes([224, e.payload_size | 128, 0])
    struct.pack_into("<I", encoded, 18, len(encoded) - 22)
    with pytest.raises(FlpWriteError, match="length"):
        verify_fl26_output(raw, bytes(encoded), intent)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only exclusive bundle publication")
def test_active_cleanup_is_replayed_from_original_midi_and_preserved(tmp_path, writer_case):
    from suno2flp.arrangement import FaithfulArrangementEngine
    from suno2flp.core.config import MidiPreferences
    from suno2flp.core.models import ArrangementOptions
    from suno2flp.flp_builder.writer_files import build_fl26_files
    from suno2flp.midi_processor import DeterministicMidiProcessor

    case = writer_case()
    original = case[0].sources[0].midi
    cleaned = DeterministicMidiProcessor().clean(
        original, MidiPreferences(quantize=True, quantize_grid_ticks=240)
    )
    arrangement = FaithfulArrangementEngine().arrange(
        [cleaned], case[0].metadata, "faithful", options=ArrangementOptions(note_view="active")
    )
    updated = (arrangement, *case[1:])
    inputs = save_case(tmp_path, updated)
    destination = tmp_path.parent / (tmp_path.name + "-cleaned-bundle")
    result = build_fl26_files(*inputs, destination)
    assert scan_template_inventory(result.output_path.read_bytes()).notes[0].position_ticks == 48
    provenance = json.loads((destination / "provenance.json").read_text())
    source = provenance["intent"]["arrangement"]["sources"][0]["midi"]
    assert source["cleanup"] and source["tracks"][1]["notes"][0]["original_start_tick"] == 120
    assert hashlib.sha256(original.source.read_bytes()).hexdigest() == original.source_sha256


@pytest.mark.skipif(os.name != "nt", reason="Windows-only exclusive bundle publication")
def test_same_inputs_in_two_new_bundles_are_deterministic(tmp_path, writer_case):
    from suno2flp.flp_builder.writer_files import build_fl26_files

    inputs = save_case(tmp_path, writer_case())
    outputs = [tmp_path.parent / (tmp_path.name + f"-bundle-{index}") for index in range(2)]
    for output in outputs:
        build_fl26_files(*inputs, output)
    for name in ("project.flp", "provenance.json", "verification.json"):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()


def test_reparse_parent_is_refused_without_requiring_junction_privilege(
    tmp_path, writer_case, monkeypatch
):
    import stat
    from types import SimpleNamespace

    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder.writer_files import build_fl26_files

    inputs = save_case(tmp_path, writer_case())
    parent = tmp_path.parent / (tmp_path.name + "-reparse")
    parent.mkdir()
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if path == parent:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(FlpWriteError, match="reparse"):
        build_fl26_files(*inputs, parent / "bundle")
    assert list(parent.iterdir()) == []


def test_unsupported_publication_platform_fails_before_staging(tmp_path, writer_case, monkeypatch):
    from types import SimpleNamespace

    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder import writer_io
    from suno2flp.flp_builder.writer_files import build_fl26_files

    inputs = save_case(tmp_path, writer_case())
    parent = tmp_path.parent / (tmp_path.name + "-platform")
    parent.mkdir()
    monkeypatch.setattr(writer_io, "os", SimpleNamespace(name="posix"))
    with pytest.raises(FlpWriteError, match="writer_publish_unavailable"):
        build_fl26_files(*inputs, parent / "bundle")
    assert list(parent.iterdir()) == []


@pytest.mark.parametrize(
    "fault,code", [("version", "writer_version_bytes"), ("mixed_bases", "writer_clip_base")]
)
def test_unassessed_frame_or_clip_base_policies_block(writer_case, fault, code):
    arrangement, inspection, bindings, _, backend = writer_case()
    raw = bytearray(inspection.template_path.read_bytes())
    if fault == "version":
        first = inspection.inventory.events[0]
        payload = raw[first.payload_offset : first.payload_offset + first.payload_size - 1]
        raw[first.file_offset : first.payload_offset + first.payload_size] = event(199, payload)
        struct.pack_into("<I", raw, 18, len(raw) - 22)
    else:
        clip = inspection.inventory.clips[1]
        struct.pack_into("<HH", raw, clip.file_offset + 4, 3, 5)
    replace_inventory(inspection, bindings, bytes(raw))
    local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
    (
        inspection.local_summary,
        inspection.backend_summary_status,
        inspection.backend_summary_mismatches,
    ) = local, status, mismatch
    policy = policy_for(inspection, bindings)
    intent = intent_for((arrangement, inspection, bindings, policy, backend))
    assert intent.status == "blocked" and code in {d.code for d in intent.diagnostics}


def test_unreviewed_draft_can_report_blockers_without_fabricating_attestations(writer_case):
    from suno2flp.core.writer_models import Fl26WriterPolicy, WriterPolicyDocument

    case = writer_case()
    data = case[3].config.model_dump()
    data.update(
        reference_kind="unverified",
        dependency_review="unverified",
        instrument_review="unverified",
        local_use_review="unverified",
        targets=[],
    )
    draft = WriterPolicyDocument(config=Fl26WriterPolicy.model_validate(data))
    intent = intent_for((*case[:3], draft, case[4]))
    assert intent.status == "blocked" and intent.reference_kind == "unverified"
    assert "writer_review_unverified" in {d.code for d in intent.diagnostics}


def test_previously_rounded_arrangement_is_not_promoted_to_exact_writer(writer_case):
    from suno2flp.arrangement import FaithfulArrangementEngine
    from suno2flp.core.models import ArrangementOptions

    case = writer_case(start=121)
    arrangement = FaithfulArrangementEngine().arrange(
        [case[0].sources[0].midi],
        case[0].metadata,
        "faithful",
        options=ArrangementOptions(target_ppq=96, ppq_rounding="nearest"),
    )
    assert arrangement.tracks[1].notes[0].start_tick == 24
    intent = intent_for((arrangement, *case[1:]))
    assert intent.status == "blocked"
    assert "writer_source_rounding" in {d.code for d in intent.diagnostics}


def test_unbound_empty_note_event_is_blocked_before_encoding(writer_case):
    arrangement, inspection, bindings, _, backend = writer_case()
    raw = bytearray(inspection.template_path.read_bytes())
    raw.extend(event(65, b"\x03\0") + event(224, b""))
    struct.pack_into("<I", raw, 18, len(raw) - 22)
    replace_inventory(inspection, bindings, bytes(raw))
    inspection.project.patterns.append({"id": 2, "name": "unbound empty Pattern", "noteCount": 0})
    local, status, mismatch = compare_backend_summary(inspection.inventory, inspection.project)
    (
        inspection.local_summary,
        inspection.backend_summary_status,
        inspection.backend_summary_mismatches,
    ) = local, status, mismatch
    intent = intent_for(
        (arrangement, inspection, bindings, policy_for(inspection, bindings), backend)
    )
    assert intent.status == "blocked"
    assert "writer_inherited_content" in {d.code for d in intent.diagnostics}
