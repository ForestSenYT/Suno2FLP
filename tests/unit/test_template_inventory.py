"""Original byte fixtures; no backend, project editing or writer is used."""

import hashlib
import json
import struct

import pytest

from suno2flp.core.errors import TemplateInspectionError


def event(event_id, payload):
    prefix = bytearray([event_id])
    if event_id >= 192:
        length = len(payload)
        while length >= 128:
            prefix.append((length & 127) | 128)
            length >>= 7
        prefix.append(length)
    return bytes(prefix) + payload


def original_template(events=b"", *, channels=2, version="25.1.2.4896", suffix=b""):
    data = event(199, version.encode() + b"\0") + events
    return (
        b"FLhd"
        + struct.pack("<IHHH", 6, 0, channels, 96)
        + b"FLdt"
        + struct.pack("<I", len(data))
        + data
        + suffix
    )


def note(*, channel=0, position=121, length=49, flags=0):
    record = bytearray(24)
    struct.pack_into("<iHBBi", record, 0, position, flags, channel, 0, length)
    record[12], record[20], record[21] = 60, 64, 90
    return bytes(record)


def clip(*, item=3, base=2, track=4, start=0.125, end=0.0, flags=0, size=80):
    record = bytearray(size)
    struct.pack_into(
        "<iHHiHHHHIff", record, 0, 241, base, item, 193, 499 - track, 0, 0, flags, 0, start, end
    )
    return bytes(record)


def scan(raw):
    from suno2flp.integrations.template_inventory import scan_template_inventory

    return scan_template_inventory(raw)


def test_notes_clips_crops_have_exact_file_and_event_provenance():
    source_note = note()
    source_clip = clip(flags=0x2000)
    raw = original_template(
        event(65, b"\x01\0") + event(224, source_note) + event(233, source_clip)
    )
    result = scan(raw)
    assert result.coverage == "decoded" and result.ppq == 96
    assert result.template_sha256 == hashlib.sha256(raw).hexdigest()
    observed = result.notes[0]
    assert (
        observed.pattern_id,
        observed.channel_id,
        observed.position_ticks,
        observed.length_ticks,
    ) == (0, 0, 121, 49)
    assert observed.raw_hex == source_note.hex()
    assert raw[observed.file_offset : observed.file_offset + 24] == source_note
    observed_clip = result.clips[0]
    assert (observed_clip.kind, observed_clip.item_id, observed_clip.track) == ("pattern", 0, 4)
    assert observed_clip.muted and observed_clip.raw_hex == source_clip.hex()
    assert observed_clip.start_offset.value == 0.125
    assert observed_clip.start_offset.raw_hex == struct.pack("<f", 0.125).hex()
    assert (observed_clip.position_ticks, observed_clip.length_ticks) == (241, 193)
    assert (
        result.events[observed.event_index].payload_sha256
        == hashlib.sha256(source_note).hexdigest()
    )
    assert json.loads(result.model_dump_json())["clips"][0]["start_offset"]["value"] == 0.125


@pytest.mark.parametrize(
    "tail", [b"\xe0\x80", b"\xe0\xff\xff\xff\xff\x7f", b"\xe0\x18\0", b"\x40\0"]
)
def test_truncated_or_invalid_event_lengths_fail_explicitly(tail):
    with pytest.raises(TemplateInspectionError, match="template_inventory_invalid"):
        scan(original_template(tail))


@pytest.mark.parametrize("suffix", [b"x", b"FLdt\0\0\0\0", b"JUNK\x04\0\0\0oops"])
def test_trailing_or_extra_chunks_are_not_silently_ignored(suffix):
    if suffix == b"x":
        with pytest.raises(TemplateInspectionError, match="template_inventory_invalid"):
            scan(original_template(suffix=suffix))
    else:
        result = scan(original_template(suffix=suffix))
        assert result.coverage == "partial"
        assert result.chunks[-1].payload_sha256 == hashlib.sha256(suffix[8:]).hexdigest()


def test_automation_links_and_points_preserve_float_bits_without_rounding():
    link = struct.pack("<HBIBHhQ", 0, 1, 0, 0, 0x8002, 0, 0)
    header = bytes(17) + struct.pack("<I", 2)
    point1 = struct.pack("<ddfI", 0.125, 0.3, 0.5, 7)
    point2 = struct.pack("<ddfI", 0.25, 0.8, 0.25, 9)
    payload = header + point1 + point2 + b"unknown-tail"
    raw = original_template(event(227, link) + event(64, b"\x01\0") + event(234, payload))
    inventory = scan(raw)
    assert [item.kind for item in inventory.automation] == ["links", "points"]
    links, points = inventory.automation
    assert links.links[0].automation_channel_id == 1
    assert links.links[0].parameter_raw == 0x8002
    assert points.channel_id == 1 and points.raw_hex == payload.hex()
    assert [point.encoded_time.value for point in points.points] == [0.125, 0.25]
    assert points.points[1].raw_hex == point2.hex()
    assert points.tail_hex == b"unknown-tail".hex()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_crops_retain_bits_and_mark_inventory_partial(value):
    raw_clip = clip(start=value)
    result = scan(original_template(event(233, raw_clip)))
    assert result.coverage == "partial"
    assert result.clips[0].start_offset.value is None
    assert result.clips[0].start_offset.raw_hex == raw_clip[24:28].hex()
    assert "NaN" not in result.model_dump_json() and "Infinity" not in result.model_dump_json()


@pytest.mark.parametrize(
    "events",
    [
        event(224, note()),
        event(65, b"\x01\0") + event(224, b"bad"),
        event(233, bytes(60)),
        event(235, bytes(80)),
        event(234, bytes(20)),
        event(250, b"opaque"),
    ],
)
def test_unsupported_or_ambiguous_structure_retains_evidence_and_blocks_coverage(events):
    result = scan(original_template(events))
    assert result.coverage == "partial" and result.diagnostics
    assert result.events[-1].payload_sha256


def test_unsupported_version_does_not_guess_record_layouts():
    result = scan(original_template(event(233, bytes(80)), version="99.0.0.1"))
    assert result.coverage == "unsupported" and not result.clips


@pytest.mark.parametrize("fault", ["missing_points", "point_location", "missing_automation"])
def test_serialized_automation_cannot_lose_decoded_records_or_locations(fault):
    from pydantic import ValidationError

    from suno2flp.core.template_inventory import TemplateInventory

    payload = bytes(17) + struct.pack("<I", 1) + struct.pack("<ddfI", 0.125, 0.3, 0.5, 0)
    inventory = scan(original_template(event(64, b"\0\0") + event(234, payload)))
    data = inventory.model_dump()
    if fault == "missing_points":
        data["automation"][0]["points"] = []
    elif fault == "point_location":
        data["automation"][0]["points"][0]["file_offset"] += 1
    else:
        data["automation"] = []
    with pytest.raises(ValidationError):
        TemplateInventory.model_validate(data)


def test_scanner_has_no_file_or_process_access(monkeypatch):
    from pathlib import Path

    from suno2flp.core.template_inventory import TemplateInventory

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only byte scanner accessed a file or process")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    result = scan(original_template(event(65, b"\x01\0") + event(224, note())))
    assert TemplateInventory.model_validate_json(result.model_dump_json()) == result
