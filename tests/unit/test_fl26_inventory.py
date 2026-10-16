"""Independently authored synthetic FL26 inputs; no user bytes are distributed."""

import hashlib
import struct

import pytest
from pydantic import ValidationError
from test_template_inspection import inspection_setup as inspection_setup

from suno2flp.core.errors import TemplateInspectionError
from suno2flp.core.template_inventory import TemplateInventory
from suno2flp.integrations.template_inventory import scan_template_inventory

FL26 = "26.1.7.5654"
FL25 = "25.1.2.4896"


def event(kind, payload):
    prefix = bytearray([kind])
    if kind >= 192:
        length = len(payload)
        while length >= 128:
            prefix.append((length & 127) | 128)
            length >>= 7
        prefix.append(length)
    return bytes(prefix) + payload


def project(events):
    return (
        b"FLhd"
        + struct.pack("<IHHH", 6, 0, 1, 96)
        + b"FLdt"
        + struct.pack("<I", len(events))
        + events
    )


def fixture_bytes(*, version=FL26, stride=88, copies=1, sentinel=False, extra=b""):
    note = bytearray(24)
    struct.pack_into("<iHBBi", note, 0, 120, 0x4000, 0, 0, 240)
    note[12], note[20], note[21] = 60, 64, 90
    clip = bytearray(stride)
    struct.pack_into("<iHHiHH", clip, 0, 0, 1, 2, 384, 499, 0)
    struct.pack_into("<ff", clip, 24, 0.125, 0.0)
    if sentinel:
        clip[24:32] = b"\xff" * 8
    if stride == 88:
        clip[80:] = bytes.fromhex("123456789abcdef0")
    events = event(199, version.encode() + b"\0")
    events += event(172, b"\x01\x01\0" if version == FL26 else b"\x01\x01\0\0")
    events += event(192, "Fixture\0".encode("utf-16-le"))
    events += event(156, struct.pack("<I", 130000))
    events += event(65, b"\x01\0") + event(224, note) + event(233, clip * copies) + extra
    return project(events)


def test_exact_fl26_profile_retains_three_byte_172_and_88_byte_clip():
    raw = fixture_bytes()
    inventory = scan_template_inventory(raw)
    assert inventory.coverage == "decoded"
    assert inventory.schema_version == 2 and inventory.reader.endswith("-v2")
    assert inventory.profile_id == "fl26-26.1.7.5654-read-v1"
    assert [e.event_id for e in inventory.events] == [199, 172, 192, 156, 65, 224, 233]
    override = inventory.events[1]
    assert override.payload_size == 3 and override.scalar_hex == "010100"
    assert override.framing_rule == "fl26-event-172-3bytes" and override.header_hex == "ac"
    clip = inventory.clips[0]
    assert clip.record_size == 88 and clip.extension_hex == "123456789abcdef0"
    assert raw[clip.file_offset : clip.file_offset + 88].hex() == clip.raw_hex
    assert inventory.notes[0].position_ticks == 120
    assert inventory.notes[0].length_ticks == 240
    assert clip.start_offset.value == 0.125
    assert inventory.template_sha256 == hashlib.sha256(raw).hexdigest()
    assert TemplateInventory.model_validate_json(inventory.model_dump_json()) == inventory


def test_fl25_keeps_classic_event_width_and_80_byte_records():
    raw = fixture_bytes(version=FL25, stride=80)
    inventory = scan_template_inventory(raw)
    assert inventory.events[1].scalar_hex == "01010000"
    assert inventory.events[1].framing_rule == "classic"
    assert inventory.clips[0].record_size == 80 and inventory.clips[0].extension_hex == ""
    assert inventory.profile_id == "fl25-25.1.2.4896-read-v1"


def test_genuine_v1_inventory_fields_still_load_without_inventing_profile_metadata():
    data = scan_template_inventory(fixture_bytes(version=FL25, stride=80)).model_dump()
    data.update(schema_version=1, reader="suno2flp-flp-inventory-v1")
    del data["profile_id"]
    for entry in data["events"]:
        del entry["header_hex"]
        del entry["framing_rule"]
    del data["clips"][0]["extension_hex"]
    result = TemplateInventory.model_validate(data)
    assert result.schema_version == 1 and result.profile_id is None
    assert result.clips[0].record_size == 80


@pytest.mark.parametrize("version,stride", [(FL26, 80), (FL25, 88)])
def test_record_width_never_falls_back_across_profiles(version, stride):
    result = scan_template_inventory(fixture_bytes(version=version, stride=stride))
    assert result.coverage == "partial" and not result.clips
    assert any(item.code == "inventory_playlist_unsupported" for item in result.diagnostics)


@pytest.mark.parametrize("version,stride,count", [(FL26, 88, 10), (FL25, 80, 11)])
def test_lengths_divisible_by_both_strides_use_only_selected_profile(version, stride, count):
    inventory = scan_template_inventory(fixture_bytes(version=version, stride=stride, copies=count))
    assert len(inventory.clips) == count
    assert {clip.record_size for clip in inventory.clips} == {stride}
    assert inventory.clips[-1].file_offset == inventory.clips[0].file_offset + stride * (count - 1)


@pytest.mark.parametrize("payload", [b"", b"\x01", b"\x01\x01"])
def test_truncated_three_byte_event_fails_without_consuming_invented_data(payload):
    raw = project(event(199, FL26.encode() + b"\0") + event(172, payload))
    with pytest.raises(TemplateInspectionError, match="template_inventory_invalid"):
        scan_template_inventory(raw)


@pytest.mark.parametrize(
    "events",
    [
        event(172, b"\x01\x01\0") + event(199, FL26.encode() + b"\0"),
        event(199, b"26.1.7.5655\0") + event(172, b"\x01\x01\0"),
        event(199, b"\xff\0") + event(172, b"\x01\x01\0"),
        event(199, FL26.encode() + b"\0") + event(199, FL26.encode() + b"\0"),
        event(199, FL26.encode() + b"\0") + event(199, FL25.encode() + b"\0"),
    ],
)
def test_late_unknown_or_conflicting_version_cannot_enable_override(events):
    with pytest.raises(TemplateInspectionError, match="template_inventory_invalid"):
        scan_template_inventory(project(events))


@pytest.mark.parametrize(
    "early", [event(233, bytes(88)), event(65, b"\x01\0") + event(224, bytes(24))]
)
def test_version_must_precede_record_interpretation_not_only_event_172(early):
    with pytest.raises(TemplateInspectionError, match="template_inventory_invalid"):
        scan_template_inventory(project(early + event(199, FL26.encode() + b"\0")))


def test_nonfinite_fl26_crop_bits_and_extensions_survive_without_tick_conversion():
    result = scan_template_inventory(fixture_bytes(sentinel=True))
    assert result.coverage == "partial"
    assert result.clips[0].start_offset.raw_hex == "ffffffff"
    assert result.clips[0].start_offset.value is None
    assert result.clips[0].end_offset.value is None
    assert result.clips[0].extension_hex == "123456789abcdef0"


@pytest.mark.parametrize("fault", ["extension", "location", "profile", "override_rule"])
def test_loaded_inventory_rejects_lost_extension_or_false_profile_provenance(fault):
    result = scan_template_inventory(fixture_bytes())
    data = result.model_dump()
    if fault == "extension":
        data["clips"][0]["extension_hex"] = "00" * 8
    elif fault == "location":
        data["clips"][0]["file_offset"] += 8
    elif fault == "profile":
        data["profile_id"] = "fl25-25.1.2.4896-read-v1"
    else:
        data["events"][1]["framing_rule"] = "classic"
    with pytest.raises(ValidationError):
        TemplateInventory.model_validate(data)


def test_inspection_exposes_fl26_backend_false_success_without_replacing_evidence(inspection_setup):
    from suno2flp.integrations.music2daw import Music2DawInspector

    backend, template, payload, calls = inspection_setup
    original = fixture_bytes()
    template.write_bytes(original)
    payload.update(flStudioVersion=FL26, tempo=140, playlistItemCount=0, patterns=[])
    result = Music2DawInspector(backend).inspect(template)
    assert result.project.tempo == 140 and result.project.patterns == []
    assert result.local_summary.tempo_millibpm == 130000
    assert result.local_summary.pattern_note_counts == {0: 1}
    assert result.local_summary.playlist_item_count == 1
    assert result.backend_summary_status == "inconsistent"
    assert {m.field for m in result.backend_summary_mismatches} == {
        "tempo",
        "patterns",
        "playlist_item_count",
    }
    assert all(m.event_indices for m in result.backend_summary_mismatches)
    assert any(d.code == "backend_summary_inconsistent" for d in result.diagnostics)
    assert result.inventory.profile_id == "fl26-26.1.7.5654-read-v1"
    assert len(calls) == 2 and template.read_bytes() == original
    assert result.template_sha256_before == result.template_sha256_after
    assert result.compatibility == "unverified"


def test_consistent_summary_is_only_agreement_with_selected_byte_families(inspection_setup):
    from suno2flp.integrations.music2daw import Music2DawInspector

    backend, template, payload, _ = inspection_setup
    original = fixture_bytes(version=FL25, stride=80)
    template.write_bytes(original)
    payload.update(
        tempo=130, playlistItemCount=1, patterns=[{"id": 0, "name": "Fixture", "noteCount": 1}]
    )
    result = Music2DawInspector(backend).inspect(template)
    assert result.backend_summary_status == "consistent"
    assert not result.backend_summary_mismatches
    assert result.local_summary.scope == "selected_event_families_only"
    assert result.compatibility == "unverified" and template.read_bytes() == original


def test_incomplete_note_records_are_not_summarized_as_an_empty_pattern(inspection_setup):
    from suno2flp.integrations.music2daw import Music2DawInspector

    backend, template, payload, _ = inspection_setup
    raw = project(
        event(199, FL26.encode() + b"\0")
        + event(156, struct.pack("<I", 130000))
        + event(65, b"\x01\0")
        + event(224, b"partial")
    )
    template.write_bytes(raw)
    payload.update(flStudioVersion=FL26, tempo=130, patterns=[])
    result = Music2DawInspector(backend).inspect(template)
    assert result.local_summary.pattern_note_counts is None
    assert result.backend_summary_status == "unchecked"
    assert result.inventory.coverage == "partial"
