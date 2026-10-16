"""Authored scalar/record probes, never copied private FLP records."""

import struct

import pytest
from test_build_planning import planning_case as planning_case
from test_build_planning import replace_inventory
from test_fl26_inventory import event, project
from test_fl26_writer import intent_for, policy_for
from test_fl26_writer import writer_case as writer_case

from suno2flp.flp_builder.assessment import assess_template
from suno2flp.integrations.template_inventory import scan_template_inventory

PROFILE = "fl26-26.1.7.5654-read-v1"


def scalar_probe(*, flags=0x4000, crop=(-1, -1), clip_flags=0x8040, length=384):
    note = bytearray(24)
    struct.pack_into("<iHBBi", note, 0, 24, flags, 0, 0, 96)
    note[12] = 67
    struct.pack_into("<HHBB", note, 16, 120, 64, 64, 90)
    note[22:24] = b"\x80\x80"
    clip = bytearray(88)
    struct.pack_into("<iHHiHH", clip, 0, 0, 2, 3, length, 499, 0)
    struct.pack_into("<H", clip, 18, clip_flags)
    struct.pack_into("<ii", clip, 24, *crop)
    return project(
        event(199, b"26.1.7.5654\0") + event(65, b"\x01\0") + event(224, note) + event(233, clip)
    )


def ordinary_case(writer_case):
    arrangement, inspection, bindings, _, backend = writer_case()
    raw = bytearray(inspection.template_path.read_bytes())
    for note in inspection.inventory.notes:
        struct.pack_into("<H", raw, note.file_offset + 4, 0x4000)
        struct.pack_into("<HHB", raw, note.file_offset + 16, 120, 64, 64)
        raw[note.file_offset + 22 : note.file_offset + 24] = b"\x80\x80"
    replace_inventory(inspection, bindings, bytes(raw))
    return arrangement, inspection, bindings, policy_for(inspection, bindings), backend


def test_ordinary_host_attribute_form_resolves_only_that_readiness_finding(writer_case):
    _, inspection, _, _, _ = ordinary_case(writer_case)
    report = assess_template(inspection.template_path.read_bytes(), inspection)
    codes = {f.code for f in report.findings}
    assert "note_attributes_unresolved" not in codes
    assert "ordinary_note_attributes_observed" in codes
    assert report.writer_status == "blocked" and report.execution_allowed is False
    assert report.compatibility == "unverified"


def test_reviewed_ordinary_attributes_survive_encoding_and_independent_verification(writer_case):
    from suno2flp.flp_builder.fl26_codec import encode_fl26
    from suno2flp.flp_builder.fl26_verify import verify_fl26_output

    case = ordinary_case(writer_case)
    raw = case[1].template_path.read_bytes()
    intent = intent_for(case)
    assert intent.status == "ready"
    output = encode_fl26(raw, intent)
    proof = verify_fl26_output(raw, output, intent)
    notes = scan_template_inventory(output).notes
    assert [(n.position_ticks, n.length_ticks, n.channel_id) for n in notes] == [
        (24, 48, 0),
        (48, 24, 1),
    ]
    assert [(n.flags, n.fine_pitch, n.release, n.pan) for n in notes] == [
        (0x4000, 120, 64, 64),
        (0x4000, 120, 64, 64),
    ]
    assert all(bytes.fromhex(n.raw_hex)[22:24] == b"\x80\x80" for n in notes)
    assert proof.compatibility == "unverified"


@pytest.mark.parametrize("offset", [4, 5, 7, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23])
def test_nearby_unobserved_note_attributes_remain_writer_blocked(writer_case, offset):
    case = ordinary_case(writer_case)
    a, inspection, bindings, _, backend = case
    raw = bytearray(inspection.template_path.read_bytes())
    raw[inspection.inventory.notes[0].file_offset + offset] ^= 1
    replace_inventory(inspection, bindings, bytes(raw))
    intent = intent_for((a, inspection, bindings, policy_for(inspection, bindings), backend))
    assert intent.status == "blocked"
    assert "writer_note_attributes" in {d.code for d in intent.diagnostics}


@pytest.mark.parametrize("flags,expected", [(0x4000, "ordinary"), (0x4008, "slide"), (8, None)])
def test_exact_positive_note_form_and_slide_are_distinguished(flags, expected):
    from suno2flp.core.fl26_fields import note_attribute_form

    note = scan_template_inventory(scalar_probe(flags=flags)).notes[0]
    assert note_attribute_form(note, PROFILE) == expected
    assert note_attribute_form(note, "fl25-25.1.2.4896-read-v1") is None
    assert note_attribute_form(note, None) is None


@pytest.mark.parametrize(
    "crop,flags,length,form,start,end",
    [
        ((-1, -1), 0x8040, 384, "default_sentinel", None, None),
        ((96, 384), 0x40, 288, "explicit_ticks", 96, 384),
        ((96, 288), 0x40, 192, "explicit_ticks", 96, 288),
    ],
)
def test_pattern_crop_units_are_integers_without_overwriting_legacy_float_projection(
    crop, flags, length, form, start, end
):
    from suno2flp.core.fl26_fields import pattern_crop_observation
    from suno2flp.core.template_inventory import TemplateInventory

    inventory = scan_template_inventory(scalar_probe(crop=crop, clip_flags=flags, length=length))
    before = inventory.model_dump_json()
    observation = pattern_crop_observation(inventory.clips[0], PROFILE)
    assert observation is not None
    assert (observation.form, observation.start_ticks, observation.end_ticks) == (form, start, end)
    assert inventory.clips[0].start_offset.raw_hex == struct.pack("<i", crop[0]).hex()
    if form == "explicit_ticks":
        assert inventory.clips[0].start_offset.value != start
    else:
        assert inventory.clips[0].start_offset.value is None
    assert inventory.model_dump_json() == before
    assert TemplateInventory.model_validate_json(before) == inventory


@pytest.mark.parametrize(
    "crop,flags,length",
    [
        ((-1, -1), 0x40, 384),
        ((-1, 384), 0x8040, 384),
        ((0, -1), 0x8040, 384),
        ((-2, -2), 0x8040, 384),
        ((96, 384), 0x8040, 288),
        ((96, 384), 0x2040, 288),
        ((96, 384), 0x40, 287),
        ((384, 96), 0x40, 288),
        ((-96, 192), 0x40, 288),
        ((96, 96), 0x40, 0),
        ((0, 0), 0x40, 384),
    ],
)
def test_mixed_sentinels_other_flags_and_inconsistent_crop_spans_are_unresolved(
    crop, flags, length
):
    from suno2flp.core.fl26_fields import pattern_crop_observation

    clip = scan_template_inventory(scalar_probe(crop=crop, clip_flags=flags, length=length)).clips[
        0
    ]
    assert pattern_crop_observation(clip, PROFILE) is None


@pytest.mark.parametrize("change", ["profile", "channel", "group"])
def test_crop_observation_does_not_spread_to_other_layouts_or_channel_clips(change):
    from suno2flp.core.fl26_fields import pattern_crop_observation

    raw = bytearray(scalar_probe())
    clip = scan_template_inventory(raw).clips[0]
    if change == "channel":
        struct.pack_into("<H", raw, clip.file_offset + 6, 1)
    elif change == "group":
        struct.pack_into("<H", raw, clip.file_offset + 14, 1)
    clip = scan_template_inventory(bytes(raw)).clips[0]
    assert pattern_crop_observation(clip, None if change == "profile" else PROFILE) is None


@pytest.mark.parametrize("offset", [4, 7, 16, 22, 23])
def test_independent_verifier_rejects_changes_to_preserved_ordinary_attributes(writer_case, offset):
    from suno2flp.core.errors import FlpWriteError
    from suno2flp.flp_builder.fl26_codec import encode_fl26
    from suno2flp.flp_builder.fl26_verify import verify_fl26_output

    case = ordinary_case(writer_case)
    raw, intent = case[1].template_path.read_bytes(), intent_for(case)
    assert intent.status == "ready"
    output = bytearray(encode_fl26(raw, intent))
    note = scan_template_inventory(bytes(output)).notes[0]
    output[note.file_offset + offset] ^= 1
    with pytest.raises(FlpWriteError, match="writer_round_trip_failed"):
        verify_fl26_output(raw, bytes(output), intent)


@pytest.mark.parametrize("flags,length", [(0x4008, 96), (0x4000, 0)])
def test_slide_and_zero_length_do_not_gain_ordinary_write_eligibility(writer_case, flags, length):
    a, inspection, bindings, _, backend = ordinary_case(writer_case)
    raw = bytearray(inspection.template_path.read_bytes())
    n = inspection.inventory.notes[0]
    struct.pack_into("<H", raw, n.file_offset + 4, flags)
    struct.pack_into("<i", raw, n.file_offset + 8, length)
    replace_inventory(inspection, bindings, bytes(raw))
    report = assess_template(bytes(raw), inspection)
    assert "note_attributes_unresolved" in {f.code for f in report.findings}
    intent = intent_for((a, inspection, bindings, policy_for(inspection, bindings), backend))
    assert intent.status == "blocked"
    assert "writer_note_attributes" in {d.code for d in intent.diagnostics}
    if length == 0:
        assert "writer_note_range" in {d.code for d in intent.diagnostics}


@pytest.mark.parametrize(
    "crop,flags,length,code",
    [
        ((-1, -1), 0x8040, 384, "pattern_crop_default_observed"),
        ((96, 384), 0x40, 288, "pattern_crop_ticks_observed"),
        ((96, 288), 0x40, 192, "pattern_crop_ticks_observed"),
    ],
)
def test_observed_crops_have_linked_findings_but_never_authorize_writes(
    writer_case, crop, flags, length, code
):
    a, inspection, bindings, _, backend = ordinary_case(writer_case)
    raw = bytearray(inspection.template_path.read_bytes())
    clip = inspection.inventory.clips[0]
    struct.pack_into("<H", raw, clip.file_offset + 18, flags)
    struct.pack_into("<i", raw, clip.file_offset + 8, length)
    struct.pack_into("<ii", raw, clip.file_offset + 24, *crop)
    replace_inventory(inspection, bindings, bytes(raw))
    report = assess_template(bytes(raw), inspection)
    finding = next(f for f in report.findings if f.code == code)
    assert finding.event_indices == [clip.event_index] and finding.clip_indices == [0]
    assert "crop_semantics_unresolved" not in {f.code for f in report.findings}
    assert report.execution_allowed is False
    policy = policy_for(inspection, bindings)
    policy.config.reference_kind = "operator_host_readback"
    intent = intent_for((a, inspection, bindings, policy, backend))
    assert intent.status == "blocked"
    assert "writer_crop" in {d.code for d in intent.diagnostics}


def test_ordinary_attribute_exception_does_not_bypass_pinned_policy_or_prototype_hashes(
    writer_case,
):
    old_policy = writer_case()[3]
    # Use this case's actual paths and byte-linked bindings, with the old scalar-row hashes.
    a, inspection, bindings, policy, backend = ordinary_case(writer_case)
    policy.config.targets[0].note_sha256 = old_policy.config.targets[0].note_sha256
    intent = intent_for((a, inspection, bindings, policy, backend))
    assert intent.status == "blocked"
    assert "writer_prototype_unverified" in {d.code for d in intent.diagnostics}
