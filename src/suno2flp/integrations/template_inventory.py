"""Original read-only FLP inventory scanner for a narrow, source-assessed layout.

This module has no file/process access and no encoder. Unknown payloads are hashed,
not guessed; raw note/clip/automation records retain uninterpreted bytes.
"""

import hashlib
import struct
from typing import Literal

from suno2flp.core.backend_models import FlpHeader
from suno2flp.core.errors import TemplateInspectionError
from suno2flp.core.models import Diagnostic
from suno2flp.core.template_inventory import (
    AutomationLink,
    AutomationPoint,
    ChunkEvidence,
    FloatEvidence,
    TemplateAutomationEvent,
    TemplateClipRecord,
    TemplateEventEvidence,
    TemplateInventory,
    TemplateNoteRecord,
    clip_fields,
    note_fields,
)
from suno2flp.core.template_profiles import FL26_READ_PROFILE, read_profile

# Only inspected scalar/text and opaque plugin-state families are exempted here.
# Opaque plugin state remains semantically unverified, even with decoded coverage.
PASSIVE_EVENTS = {
    0,
    12,
    17,
    18,
    21,
    64,
    65,
    66,
    99,
    128,
    135,
    149,
    156,
    192,
    193,
    194,
    195,
    196,
    197,
    198,
    199,
    201,
    203,
    204,
    206,
    207,
    212,
    213,
    219,
}


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _framing(
    raw: bytes,
) -> tuple[FlpHeader, list[ChunkEvidence], list[tuple[int, int, int, bytes]]]:
    if len(raw) < 22 or raw[:4] != b"FLhd":
        raise ValueError("Expected an FLhd project and complete chunk header")
    length, format_id, channels, ppq = struct.unpack_from("<IHHH", raw, 4)
    if length != 6:
        raise ValueError("Unsupported FLhd length")
    header = FlpHeader(format=format_id, channel_count=channels, ppq=ppq)
    chunks = []
    events = []
    cursor = 14
    declared_version = None
    version_seen = False
    while cursor < len(raw):
        if len(raw) - cursor < 8:
            raise ValueError("Truncated chunk header or trailing bytes")
        chunk_length = struct.unpack_from("<I", raw, cursor + 4)[0]
        end = cursor + 8 + chunk_length
        if end > len(raw):
            raise ValueError("Chunk payload extends beyond template bytes")
        chunks.append(
            ChunkEvidence(
                id_hex=raw[cursor : cursor + 4].hex(),
                file_offset=cursor,
                payload_size=chunk_length,
                payload_sha256=_hash(raw[cursor + 8 : end]),
            )
        )
        if raw[cursor : cursor + 4] == b"FLdt":
            position = cursor + 8
            while position < end:
                event_offset = position
                event_id = raw[position]
                position += 1
                if event_id in {223, 224, 227, 233, 234} and not version_seen:
                    raise ValueError(
                        "Version event must precede version-dependent inventory records"
                    )
                if event_id < 192:
                    size = 1 if event_id < 64 else 2 if event_id < 128 else 4
                    if event_id == 172:
                        profile = read_profile(declared_version)
                        if profile is None:
                            raise ValueError(
                                "Event 172 requires a preceding exact assessed version"
                            )
                        size = profile.event_172_size
                else:
                    size = 0
                    for shift in range(0, 35, 7):
                        if position >= end:
                            raise ValueError("Truncated variable-length event prefix")
                        value = raw[position]
                        position += 1
                        if shift == 28 and value > 7:
                            raise ValueError("Event length exceeds signed 32-bit limit")
                        size |= (value & 127) << shift
                        if value < 128:
                            break
                    else:
                        raise ValueError("Unterminated event length prefix")
                if position + size > end:
                    raise ValueError("Event payload extends beyond its FLdt chunk")
                if event_id == 199:
                    if version_seen:
                        raise ValueError(
                            "Repeated/conflicting version events cannot select a profile"
                        )
                    version_seen = True
                    try:
                        declared_version = (
                            raw[position : position + size].decode("utf-8").rstrip("\0")
                        )
                    except UnicodeError:
                        declared_version = None
                events.append((event_id, event_offset, position, raw[position : position + size]))
                position += size
        cursor = end
    if not any(chunk.id_hex == b"FLdt".hex() for chunk in chunks):
        raise ValueError("No FLdt event chunk")
    return header, chunks, events


def scan_template_inventory(raw: bytes) -> TemplateInventory:
    try:
        return _scan(raw)
    except (ValueError, struct.error) as exc:
        raise TemplateInspectionError("template_inventory_invalid", str(exc)) from exc


def _scan(raw: bytes) -> TemplateInventory:
    header, chunks, framed = _framing(raw)
    diagnostics: list[Diagnostic] = []

    def issue(code: str, message: str, index: int | None = None) -> None:
        diagnostics.append(
            Diagnostic(code=code, severity="warning", message=message, event_index=index)
        )

    if len(chunks) != 1 or chunks[0].id_hex != b"FLdt".hex():
        issue(
            "inventory_chunks_unsupported", "Only one FLdt chunk with no extra chunks is assessed"
        )
    versions = []
    for event_id, _, _, payload in framed:
        if event_id == 199:
            try:
                versions.append(payload.decode("utf-8").rstrip("\0"))
            except UnicodeError:
                issue("inventory_version_invalid", "Version event is not valid UTF-8")
    version = versions[0] if len(versions) == 1 else None
    profile = read_profile(version)
    supported = profile is not None
    if not supported:
        issue("inventory_version_unsupported", "No unique exact assessed FL25/FL26 version event")
    channel = pattern = arrangement = None
    events = []
    notes = []
    clips = []
    automation = []
    max_pattern = -1
    for index, (event_id, offset, payload_offset, payload) in enumerate(framed):
        if event_id == 64:
            channel = struct.unpack("<H", payload)[0]
            if channel >= header.channel_count:
                issue("inventory_channel_invalid", "Selected channel exceeds header count", index)
        if event_id == 65:
            encoded = struct.unpack("<H", payload)[0]
            pattern = encoded - 1 if encoded else None
            if pattern is None:
                issue(
                    "inventory_pattern_invalid",
                    "Pattern delimiters must be one-based positive IDs",
                    index,
                )
            else:
                max_pattern = max(max_pattern, pattern)
        if event_id == 99:
            arrangement = struct.unpack("<H", payload)[0]
        evidence = TemplateEventEvidence(
            event_index=index,
            event_id=event_id,
            file_offset=offset,
            payload_offset=payload_offset,
            payload_size=len(payload),
            payload_sha256=_hash(payload),
            channel_id=channel,
            scalar_hex=payload.hex() if event_id < 192 else None,
            header_hex=raw[offset:payload_offset].hex(),
            framing_rule="fl26-event-172-3bytes"
            if event_id == 172 and profile == FL26_READ_PROFILE
            else "classic",
            pattern_id=pattern,
            arrangement_id=arrangement,
        )
        events.append(evidence)
        if not supported:
            continue
        if event_id == 224:
            if pattern is None or len(payload) % 24:
                issue(
                    "inventory_notes_unsupported",
                    "Notes need a preceding Pattern and aligned 24-byte records",
                    index,
                )
                continue
            for slot in range(len(payload) // 24):
                record = payload[slot * 24 : (slot + 1) * 24]
                note = TemplateNoteRecord.model_validate(
                    {
                        "event_index": index,
                        "record_index": slot,
                        "file_offset": payload_offset + slot * 24,
                        "raw_hex": record.hex(),
                        "pattern_id": pattern,
                        **note_fields(record),
                    }
                )
                notes.append(note)
                if note.channel_id >= header.channel_count:
                    issue(
                        "inventory_note_channel_invalid", "Note channel exceeds header count", index
                    )
        elif event_id == 233:
            assert profile is not None
            stride = profile.playlist_record_size
            if not payload or len(payload) % stride:
                issue(
                    "inventory_playlist_unsupported",
                    f"Only nonempty exact-profile {stride}-byte playlist records are decoded",
                    index,
                )
                continue
            for slot in range(len(payload) // stride):
                record = payload[slot * stride : (slot + 1) * stride]
                clip = TemplateClipRecord.model_validate(
                    {
                        "event_index": index,
                        "record_index": slot,
                        "file_offset": payload_offset + slot * stride,
                        "raw_hex": record.hex(),
                        "arrangement_id": arrangement,
                        **clip_fields(record),
                    }
                )
                clips.append(clip)
                if clip.start_offset.value is None or clip.end_offset.value is None:
                    issue(
                        "inventory_crop_nonfinite",
                        "Crop bits contain a nonfinite float; no timing inferred",
                        index,
                    )
                if not 0 <= clip.track < 500:
                    issue(
                        "inventory_clip_track_invalid",
                        "Clip lane is outside assessed FL25 range",
                        index,
                    )
        elif event_id in {223, 227, 234} or (event_id == 21 and payload == b"\x05"):
            kind: Literal["channel_type", "legacy", "links", "points"] = (
                "channel_type"
                if event_id == 21
                else "legacy"
                if event_id == 223
                else "links"
                if event_id == 227
                else "points"
            )
            item = TemplateAutomationEvent(
                event_index=index,
                event_id=event_id,
                channel_id=channel,
                kind=kind,
                raw_hex=payload.hex(),
            )
            if event_id == 227:
                if len(payload) % 20:
                    issue(
                        "inventory_automation_unsupported",
                        "Automation link records are not aligned",
                        index,
                    )
                else:
                    for slot in range(len(payload) // 20):
                        record = payload[slot * 20 : (slot + 1) * 20]
                        parameter, destination = struct.unpack_from("<Hh", record, 8)
                        item.links.append(
                            AutomationLink(
                                event_index=index,
                                record_index=slot,
                                file_offset=payload_offset + slot * 20,
                                raw_hex=record.hex(),
                                automation_channel_id=record[2],
                                parameter_raw=parameter,
                                destination_raw=destination,
                            )
                        )
            elif event_id == 234:
                count = struct.unpack_from("<I", payload, 17)[0] if len(payload) >= 21 else None
                if count is None or count > (len(payload) - 21) // 24:
                    issue(
                        "inventory_automation_unsupported",
                        "Automation header/count exceeds retained payload",
                        index,
                    )
                else:
                    for slot in range(count):
                        record = payload[21 + slot * 24 : 21 + (slot + 1) * 24]
                        point = AutomationPoint(
                            event_index=index,
                            record_index=slot,
                            file_offset=payload_offset + 21 + slot * 24,
                            raw_hex=record.hex(),
                            encoded_time=FloatEvidence.decode(record[:8]),
                            value=FloatEvidence.decode(record[8:16]),
                            tension=FloatEvidence.decode(record[16:20]),
                        )
                        item.points.append(point)
                        if any(
                            value.value is None
                            for value in (point.encoded_time, point.value, point.tension)
                        ):
                            issue(
                                "inventory_automation_nonfinite",
                                "Automation contains nonfinite float bits",
                                index,
                            )
                    item.tail_hex = payload[21 + count * 24 :].hex()
            elif event_id == 223:
                issue(
                    "inventory_automation_unsupported",
                    "Legacy automation is retained without decoding",
                    index,
                )
            automation.append(item)
        elif event_id == 172 and profile == FL26_READ_PROFILE:
            if payload not in {b"\x01\x01\0", b"\0\x01\0"}:
                issue(
                    "inventory_event_172_unassessed",
                    "Unassessed event-172 value retained without interpretation",
                    index,
                )
        elif event_id not in PASSIVE_EVENTS:
            issue(
                "inventory_event_opaque",
                f"Event {event_id} remains opaque; routing/playlist candidates are not guessed",
                index,
            )
    if supported:
        for clip in clips:
            if (clip.kind == "channel" and clip.item_id >= header.channel_count) or (
                clip.kind == "pattern" and clip.item_id > max_pattern
            ):
                issue(
                    "inventory_clip_link_invalid",
                    "Clip links outside declared channel/Pattern inventory",
                    clip.event_index,
                )
    return TemplateInventory(
        template_sha256=_hash(raw),
        size_bytes=len(raw),
        fl_studio_version=version,
        profile_id=profile.identifier if profile else None,
        ppq=header.ppq,
        channel_count=header.channel_count,
        coverage="unsupported" if not supported else "partial" if diagnostics else "decoded",
        chunks=chunks,
        events=events,
        notes=notes,
        clips=clips,
        automation=automation,
        diagnostics=diagnostics,
    )
