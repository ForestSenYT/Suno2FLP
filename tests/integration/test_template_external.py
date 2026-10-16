"""Opt-in real parser checks using original temporary inputs; no backend FLP output."""

import hashlib
import os
import struct
from pathlib import Path

import pytest

from suno2flp.core.errors import TemplateInspectionError
from suno2flp.integrations.music2daw import Music2DawInspector

pytestmark = pytest.mark.external


@pytest.fixture
def real_inspector():
    directory = os.environ.get("SUNO2FLP_MUSIC2DAW_DIR")
    if not directory:
        pytest.skip("Set SUNO2FLP_MUSIC2DAW_DIR to explicitly enable the provisioned backend")
    return Music2DawInspector(Path(directory))


@pytest.fixture
def synthetic_template(tmp_path, request):
    def data(event_id, payload):
        assert len(payload) < 128
        return bytes([event_id, len(payload)]) + payload

    # Independently authored tiny original fixture, using documented event framing.
    note = bytearray(24)
    struct.pack_into("<i", note, 0, 120)
    struct.pack_into("<i", note, 8, 48)
    note[12], note[20], note[21] = 60, 64, 90
    events = data(199, b"25.1.2.4896\0") + bytes([156]) + struct.pack("<I", 120000)
    events += bytes([64, 0, 0]) + data(192, "Original fixture\0".encode("utf-16-le"))
    events += bytes([65, 1, 0]) + data(193, "One note\0".encode("utf-16-le"))
    events += data(224, note)
    # One original 80-byte FL25 pattern clip, zero-based playlist track 0.
    clip = bytearray(80)
    struct.pack_into("<HH", clip, 4, 1, 2)
    struct.pack_into("<iH", clip, 8, 192, 499)
    rich = getattr(request, "param", False)
    if rich:
        struct.pack_into("<f", clip, 24, 0.125)
    events += data(233, clip)
    if rich:
        link = struct.pack("<HBIBHhQ", 0, 1, 0, 0, 0x8002, 0, 0)
        events += data(227, link) + bytes([64, 1, 0])
        points = bytes(17) + struct.pack("<I", 2)
        points += struct.pack("<ddfI", 0.125, 0.3, 0.5, 0)
        points += struct.pack("<ddfI", 0.25, 0.8, 0.25, 0)
        events += data(234, points)
    path = tmp_path / "original-synthetic.flp"
    path.write_bytes(
        b"FLhd"
        + struct.pack("<IHHH", 6, 0, 2 if rich else 1, 96)
        + b"FLdt"
        + struct.pack("<I", len(events))
        + events
    )
    return path


def test_real_pinned_cli_inspects_metadata_without_changing_input(
    real_inspector, synthetic_template
):
    before = synthetic_template.read_bytes()
    result = real_inspector.inspect(synthetic_template)
    assert result.project.fl_studio_version == "25.1.2.4896"
    assert result.project.tempo == 120 and result.project.ppq == 96
    assert result.project.channels[0]["name"] == "Original fixture"
    assert result.project.patterns == [{"id": 0, "name": "One note", "noteCount": 1}]
    assert result.project.playlist_item_count == 1
    assert result.template_sha256_before == hashlib.sha256(before).hexdigest()
    assert result.template_sha256_after == result.template_sha256_before
    assert result.compatibility == "unverified"
    assert result.inventory.coverage == "decoded"
    assert len(result.inventory.notes) == len(result.inventory.clips) == 1
    assert not result.inventory.automation
    assert synthetic_template.read_bytes() == before


def test_real_backend_parse_failure_is_explicit_and_preserves_input(real_inspector, tmp_path):
    path = tmp_path / "original-invalid.flp"
    # Framing is valid; semantic orphan notes still exercise a real backend failure.
    events = b"\xc7\x0c25.1.2.4896\0" + b"\xe0\x18" + bytes(24)
    raw = (
        b"FLhd"
        + struct.pack("<IHHH", 6, 0, 1, 96)
        + b"FLdt"
        + struct.pack("<I", len(events))
        + events
    )
    path.write_bytes(raw)
    with pytest.raises(TemplateInspectionError, match="backend_process_failed"):
        real_inspector.inspect(path)
    assert path.read_bytes() == raw


def test_real_inspection_to_dry_run_keeps_source_channel_and_never_executes(
    real_inspector, synthetic_template, tmp_path, monkeypatch
):
    import mido

    from suno2flp.arrangement import FaithfulArrangementEngine
    from suno2flp.core.build_config import load_template_bindings
    from suno2flp.core.models import MusicalMetadata
    from suno2flp.flp_builder.planning import DryRunBuildPlanner
    from suno2flp.importer import MidiFileImporter

    inspection = real_inspector.inspect(synthetic_template)
    original = synthetic_template.read_bytes()
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", channel=2, note=60, velocity=80, time=120),
                mido.Message("note_off", channel=2, note=60, time=240),
            ]
        )
    )
    midi.save(source)
    arrangement = FaithfulArrangementEngine().arrange(
        [MidiFileImporter().import_file(source)], MusicalMetadata(), "faithful"
    )
    bindings = load_template_bindings(Path("examples/template_bindings.yaml"))

    def unexpected(*args, **kwargs):
        pytest.fail("Dry-run planning invoked a process")

    monkeypatch.setattr("subprocess.run", unexpected)
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "review_required" and not plan.execution_allowed
    assert plan.parts[0].notes[0].source_channel == 2
    assert plan.parts[0].binding.template_channel_id == 0
    assert (plan.parts[0].notes[0].start_tick, plan.parts[0].notes[0].duration_ticks) == (24, 48)
    assert synthetic_template.read_bytes() == original


@pytest.mark.parametrize("synthetic_template", [True], indirect=True)
def test_real_automation_and_crop_inventory_blocks_planning_without_rounding(
    real_inspector, synthetic_template, tmp_path, monkeypatch
):
    import mido

    from suno2flp.arrangement import FaithfulArrangementEngine
    from suno2flp.core.build_config import load_template_bindings
    from suno2flp.core.models import MusicalMetadata
    from suno2flp.flp_builder.planning import DryRunBuildPlanner
    from suno2flp.importer import MidiFileImporter

    before = synthetic_template.read_bytes()
    inspection = real_inspector.inspect(synthetic_template)
    assert inspection.project.channels[1]["generator"] == "Automation"
    assert inspection.inventory.coverage == "decoded"
    assert [item.kind for item in inspection.inventory.automation] == ["links", "points"]
    assert inspection.inventory.clips[0].start_offset.value == 0.125
    assert [p.encoded_time.value for p in inspection.inventory.automation[1].points] == [
        0.125,
        0.25,
    ]
    source = tmp_path / "source.mid"
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", channel=2, note=60, velocity=80, time=120),
                mido.Message("note_off", channel=2, note=60, time=240),
            ]
        )
    )
    midi.save(source)
    arrangement = FaithfulArrangementEngine().arrange(
        [MidiFileImporter().import_file(source)], MusicalMetadata(), "faithful"
    )
    bindings = load_template_bindings(Path("examples/template_bindings.yaml"))
    bindings = type(bindings).model_validate(
        {
            "config": {
                **bindings.config.model_dump(),
                "template_sha256": inspection.template_sha256_after,
            }
        }
    )

    def unexpected(*args, **kwargs):
        pytest.fail("Planning attempted a backend invocation")

    monkeypatch.setattr("subprocess.run", unexpected)
    plan = DryRunBuildPlanner().plan(arrangement, inspection, bindings)
    assert plan.status == "blocked" and not plan.execution_allowed
    assert {"template_automation_unsupported", "template_crop_unsupported"} <= {
        d.code for d in plan.diagnostics
    }
    assert plan.parts[0].notes[0].source_channel == 2
    assert plan.parts[0].notes[0].start_tick == 24
    assert plan.inspection.inventory == inspection.inventory
    assert synthetic_template.read_bytes() == before
