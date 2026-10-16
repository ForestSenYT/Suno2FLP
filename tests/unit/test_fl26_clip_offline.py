"""Offline crop/flag safety regressions using authored records, without host claims."""

import struct

import pytest
from test_build_planning import planning_case as planning_case
from test_build_planning import replace_inventory
from test_fl26_writer import intent_for, policy_for, save_case
from test_fl26_writer import writer_case as writer_case

from suno2flp.core.errors import FlpWriteError
from suno2flp.core.fl26_fields import pattern_crop_observation
from suno2flp.core.template_inventory import TemplateInventory
from suno2flp.flp_builder.fl26_codec import encode_fl26
from suno2flp.flp_builder.fl26_verify import verify_fl26_output
from suno2flp.integrations.template_inventory import scan_template_inventory


def clip_case(writer_case, *, crop=bytes(8), flags=0, length=192, moved_note=False, **music):
    arrangement, inspection, bindings, _, backend = writer_case(**music)
    raw = bytearray(inspection.template_path.read_bytes())
    clip = inspection.inventory.clips[0]
    struct.pack_into("<i", raw, clip.file_offset + 8, length)
    struct.pack_into("<H", raw, clip.file_offset + 18, flags)
    raw[clip.file_offset + 24 : clip.file_offset + 32] = crop
    if moved_note:
        struct.pack_into("<i", raw, inspection.inventory.notes[0].file_offset, 576)
    replace_inventory(inspection, bindings, bytes(raw))
    return arrangement, inspection, bindings, policy_for(inspection, bindings), backend


@pytest.mark.parametrize(
    "length,flags,start,end,moved_note,form",
    [
        (768, 0x8040, -1, -1, False, "default_sentinel"),
        (768, 0x0040, -1, -1, False, None),
        (768, 0x0040, 0, 768, False, "explicit_ticks"),
        (192, 0x0040, 0, 192, False, "explicit_ticks"),
        (250, 0x0040, 0, 250, False, "explicit_ticks"),
        (768, 0x0040, 0, 768, True, "explicit_ticks"),
    ],
)
def test_pending_resize_candidates_keep_raw_provenance_and_fail_before_encoding(
    writer_case, length, flags, start, end, moved_note, form
):
    case = clip_case(
        writer_case,
        crop=struct.pack("<ii", start, end),
        flags=flags,
        length=length,
        moved_note=moved_note,
    )
    inspection = case[1]
    raw, mtime = inspection.template_path.read_bytes(), inspection.template_path.stat().st_mtime_ns
    before = [item.model_dump_json() for item in case[:4]]
    intent = intent_for(case)
    assert intent.status == "blocked" and intent.compatibility == "unverified"
    assert {"writer_crop", "writer_clip_attributes"} <= {d.code for d in intent.diagnostics}
    inventory = intent.inspection.inventory
    clip = inventory.clips[0]
    assert (clip.position_ticks, clip.length_ticks, clip.flags) == (0, length, flags)
    assert struct.unpack_from("<ii", bytes.fromhex(clip.raw_hex), 24) == (start, end)
    assert raw[clip.file_offset : clip.file_offset + 88].hex() == clip.raw_hex
    assert inventory.events[clip.event_index].event_id == 233 and clip.record_index == 0
    observed = pattern_crop_observation(clip, inventory.profile_id)
    assert (observed.form if observed else None) == form
    if moved_note:
        assert inventory.notes[0].position_ticks == 576
    with pytest.raises(FlpWriteError, match="writer_blocked"):
        encode_fl26(raw, intent)
    assert [item.model_dump_json() for item in case[:4]] == before
    assert (inspection.template_path.read_bytes(), inspection.template_path.stat().st_mtime_ns) == (
        raw,
        mtime,
    )


@pytest.mark.parametrize(
    "start,duration,want_start,want_duration,want_end",
    [(120, 240, 24, 48, 72), (240, 480, 48, 96, 144), (5, 5, 1, 1, 2), (0, 1250, 0, 250, 250)],
)
def test_exact_ppq_conversion_and_matching_full_span_do_not_authorize_cropped_writes(
    writer_case, start, duration, want_start, want_duration, want_end
):
    case = clip_case(
        writer_case,
        crop=struct.pack("<ii", 0, want_end),
        flags=0x40,
        length=want_end,
        start=start,
        duration=duration,
    )
    intent = intent_for(case)
    part = intent.binding_check.parts[0]
    assert intent.arrangement.ticks_per_beat == 480 and intent.inspection.header.ppq == 96
    assert (part.notes[0].start_tick, part.notes[0].duration_ticks, part.clip_length_ticks) == (
        want_start,
        want_duration,
        want_end,
    )
    assert part.notes[0].source_channel == 2
    assert intent.arrangement.sources[0].midi.tracks[1].notes[0].start_tick == start
    assert intent.status == "blocked"
    assert {"writer_crop", "writer_clip_attributes"} <= {d.code for d in intent.diagnostics}


@pytest.mark.parametrize(
    "start_bits,end_bits",
    [
        ("00000080", "00000000"),  # negative zero is not positive-zero bits
        ("00000000", "00000080"),
        ("00000080", "00000080"),
        ("ffffffff", "ffffffff"),
        ("ffffffff", "00000000"),
        ("00000000", "ffffffff"),
        ("0000807f", "00000000"),  # infinity
        ("00000000", "000080ff"),
        ("0000c07f", "00000000"),  # distinct NaN payload, no canonicalization
        ("01000000", "00000000"),  # positive subnormal is not zero
    ],
)
def test_crop_bit_patterns_survive_json_and_cannot_be_normalized_into_write_permission(
    writer_case, start_bits, end_bits
):
    case = clip_case(writer_case, crop=bytes.fromhex(start_bits + end_bits))
    inventory = case[1].inventory
    loaded = TemplateInventory.model_validate_json(inventory.model_dump_json())
    clip = loaded.clips[0]
    assert (clip.start_offset.raw_hex, clip.end_offset.raw_hex) == (start_bits, end_bits)
    assert bytes.fromhex(clip.raw_hex)[24:32].hex() == start_bits + end_bits
    assert loaded == inventory
    case[3].config.reference_kind = "operator_host_readback"
    intent = intent_for(case)
    assert intent.status == "blocked" and "writer_crop" in {d.code for d in intent.diagnostics}


@pytest.mark.parametrize("flags", [1 << bit for bit in range(16)])
def test_no_individual_clip_flag_bit_gains_write_permission_even_with_zero_crops(
    writer_case, flags
):
    case = clip_case(writer_case, flags=flags)
    case[3].config.reference_kind = "operator_host_readback"
    intent = intent_for(case)
    codes = {d.code for d in intent.diagnostics}
    assert intent.inspection.inventory.clips[0].flags == flags
    assert intent.status == "blocked" and "writer_clip_attributes" in codes
    assert "writer_crop" not in codes  # isolate flags from the independent crop gate
    with pytest.raises(FlpWriteError, match="writer_blocked"):
        encode_fl26(case[1].template_path.read_bytes(), intent)


@pytest.mark.parametrize("offset", [18, 19, *range(24, 32)])
def test_independent_verifier_rejects_each_mutated_flag_or_crop_byte(writer_case, offset):
    case = writer_case()
    raw, intent = case[1].template_path.read_bytes(), intent_for(case)
    output = encode_fl26(raw, intent)
    proof = verify_fl26_output(raw, output, intent)
    assert proof.level == "structural_round_trip_only" and proof.compatibility == "unverified"
    clip = scan_template_inventory(output).clips[0]
    changed = bytearray(output)
    changed[clip.file_offset + offset] ^= 1
    with pytest.raises(FlpWriteError, match="writer_round_trip_failed"):
        verify_fl26_output(raw, bytes(changed), intent)
    assert case[1].template_path.read_bytes() == raw


@pytest.mark.parametrize(
    "crop,flags",
    [(b"\xff" * 8, 0x8040), (struct.pack("<ii", 0, 768), 0x40), (bytes(8), 1)],
)
def test_file_workflow_refuses_unverified_clip_fields_without_encoding_or_staging(
    tmp_path, writer_case, monkeypatch, crop, flags
):
    from suno2flp.flp_builder import writer_files

    case = clip_case(writer_case, crop=crop, flags=flags, length=768)
    paths = save_case(tmp_path, case)
    original = case[1].template_path.read_bytes(), case[1].template_path.stat().st_mtime_ns
    parent = tmp_path.parent / (tmp_path.name + "-outputs")
    parent.mkdir()

    def forbidden(*_args, **_kwargs):
        pytest.fail("Blocked clip evidence reached encoder, staging, publication or a process")

    for name in ("encode_fl26", "write_new", "publish_bundle"):
        monkeypatch.setattr(writer_files, name, forbidden)
    monkeypatch.setattr(writer_files.tempfile, "mkdtemp", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    with pytest.raises(FlpWriteError, match="writer_blocked"):
        writer_files.build_fl26_files(*paths, parent / "must-not-exist")
    assert list(parent.iterdir()) == []
    assert (
        case[1].template_path.read_bytes(),
        case[1].template_path.stat().st_mtime_ns,
    ) == original
