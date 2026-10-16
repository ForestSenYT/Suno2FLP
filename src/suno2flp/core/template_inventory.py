"""Byte-linked, read-only template evidence; decoded does not imply compatibility."""

import hashlib
import math
import struct
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import Field, model_validator

from suno2flp.core.models import Contract, Diagnostic
from suno2flp.core.template_profiles import FL26_READ_PROFILE, read_profile

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
HexBytes = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{2})*$", strict=True)]
Index = Annotated[int, Field(ge=0, strict=True)]


class FloatEvidence(Contract):
    encoding: Literal["f32le", "f64le"]
    raw_hex: HexBytes
    value: float | None = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def matches_bits(self) -> "FloatEvidence":
        raw = bytes.fromhex(self.raw_hex)
        size = 4 if self.encoding == "f32le" else 8
        if len(raw) != size:
            raise ValueError("Float evidence has the wrong byte width")
        number = struct.unpack("<f" if size == 4 else "<d", raw)[0]
        if self.value != (number if math.isfinite(number) else None):
            raise ValueError("Float value differs from retained bits")
        return self

    @classmethod
    def decode(cls, raw: bytes) -> "FloatEvidence":
        number = struct.unpack("<f" if len(raw) == 4 else "<d", raw)[0]
        return cls(
            encoding="f32le" if len(raw) == 4 else "f64le",
            raw_hex=raw.hex(),
            value=number if math.isfinite(number) else None,
        )


class ChunkEvidence(Contract):
    id_hex: HexBytes
    file_offset: Index
    payload_size: Index
    payload_sha256: Digest


class TemplateEventEvidence(Contract):
    event_index: Index
    event_id: int = Field(ge=0, le=255, strict=True)
    file_offset: Index
    payload_offset: Index
    payload_size: Index
    payload_sha256: Digest
    channel_id: int | None = None
    scalar_hex: HexBytes | None = None
    header_hex: HexBytes | None = None
    framing_rule: Literal["classic", "fl26-event-172-3bytes"] = "classic"
    pattern_id: int | None = None
    arrangement_id: int | None = None


class RecordEvidence(Contract):
    event_index: Index
    record_index: Index
    file_offset: Index
    raw_hex: HexBytes


def note_fields(raw: bytes) -> dict[str, int]:
    if len(raw) != 24:
        raise ValueError("Expected a 24-byte note")
    return {
        "position_ticks": struct.unpack_from("<i", raw)[0],
        "flags": struct.unpack_from("<H", raw, 4)[0],
        "channel_id": raw[6],
        "group": raw[7],
        "length_ticks": struct.unpack_from("<i", raw, 8)[0],
        "pitch": raw[12],
        "fine_pitch": struct.unpack_from("<H", raw, 16)[0],
        "release": struct.unpack_from("<H", raw, 18)[0],
        "pan": raw[20],
        "velocity": raw[21],
    }


class TemplateNoteRecord(RecordEvidence):
    pattern_id: Index
    channel_id: Index
    position_ticks: int
    length_ticks: int
    pitch: Index
    velocity: Index
    pan: Index
    fine_pitch: Index
    release: Index
    flags: Index
    group: Index

    @model_validator(mode="after")
    def matches_bytes(self) -> "TemplateNoteRecord":
        if any(
            getattr(self, key) != value
            for key, value in note_fields(bytes.fromhex(self.raw_hex)).items()
        ):
            raise ValueError("Note fields differ from retained record bytes")
        return self


def clip_fields(raw: bytes) -> dict[str, object]:
    if len(raw) not in {80, 88}:
        raise ValueError("Only exact-profile 80/88-byte clip records are decoded")
    position, base, item, length, reversed_track, group, _, flags = struct.unpack_from(
        "<iHHiHHHH", raw
    )
    return {
        "record_size": len(raw),
        "extension_hex": raw[80:].hex(),
        "position_ticks": position,
        "pattern_base": base,
        "encoded_item_index": item,
        "kind": "channel" if item <= base else "pattern",
        "item_id": item if item <= base else item - base - 1,
        "length_ticks": length,
        "track": 499 - reversed_track,
        "group": group,
        "flags": flags,
        "muted": bool(flags & 0x2000),
        "start_offset": FloatEvidence.decode(raw[24:28]),
        "end_offset": FloatEvidence.decode(raw[28:32]),
    }


class TemplateClipRecord(RecordEvidence):
    arrangement_id: int | None = None
    record_size: Literal[80, 88]
    extension_hex: HexBytes = ""
    pattern_base: Index
    encoded_item_index: Index
    kind: Literal["pattern", "channel"]
    item_id: Index
    position_ticks: int
    length_ticks: int
    track: int
    group: Index
    flags: Index
    muted: bool
    start_offset: FloatEvidence
    end_offset: FloatEvidence

    @model_validator(mode="after")
    def matches_bytes(self) -> "TemplateClipRecord":
        if any(
            getattr(self, key) != value
            for key, value in clip_fields(bytes.fromhex(self.raw_hex)).items()
        ):
            raise ValueError("Clip fields differ from retained record bytes")
        return self


class AutomationLink(RecordEvidence):
    automation_channel_id: Index
    parameter_raw: Index
    destination_raw: int

    @model_validator(mode="after")
    def matches_bytes(self) -> "AutomationLink":
        raw = bytes.fromhex(self.raw_hex)
        if len(raw) != 20 or (
            self.automation_channel_id,
            self.parameter_raw,
            self.destination_raw,
        ) != (raw[2], *struct.unpack_from("<Hh", raw, 8)):
            raise ValueError("Automation link differs from retained bytes")
        return self


class AutomationPoint(RecordEvidence):
    # Encoded time is retained, not promoted to an absolute/cumulative timeline.
    encoded_time: FloatEvidence
    value: FloatEvidence
    tension: FloatEvidence

    @model_validator(mode="after")
    def matches_bytes(self) -> "AutomationPoint":
        raw = bytes.fromhex(self.raw_hex)
        if len(raw) != 24 or (self.encoded_time, self.value, self.tension) != (
            FloatEvidence.decode(raw[:8]),
            FloatEvidence.decode(raw[8:16]),
            FloatEvidence.decode(raw[16:20]),
        ):
            raise ValueError("Automation point differs from retained bytes")
        return self


class TemplateAutomationEvent(Contract):
    event_index: Index
    event_id: int
    channel_id: int | None
    kind: Literal["channel_type", "legacy", "links", "points"]
    raw_hex: HexBytes
    links: list[AutomationLink] = Field(default_factory=list)
    points: list[AutomationPoint] = Field(default_factory=list)
    tail_hex: HexBytes = ""


class TemplateInventory(Contract):
    schema_version: Literal[1, 2] = 2
    reader: Literal["suno2flp-flp-inventory-v1", "suno2flp-flp-inventory-v2"] = (
        "suno2flp-flp-inventory-v2"
    )
    profile_id: Literal["fl25-25.1.2.4896-read-v1", "fl26-26.1.7.5654-read-v1"] | None = None
    template_sha256: Digest
    size_bytes: Index
    fl_studio_version: str | None
    ppq: int = Field(gt=0, le=32767)
    channel_count: int = Field(ge=1, le=1000)
    coverage: Literal["decoded", "partial", "unsupported"]
    chunks: list[ChunkEvidence]
    events: list[TemplateEventEvidence]
    notes: list[TemplateNoteRecord]
    clips: list[TemplateClipRecord]
    automation: list[TemplateAutomationEvent]
    diagnostics: list[Diagnostic]

    @model_validator(mode="after")
    def consistent_locations(self) -> "TemplateInventory":
        profile = read_profile(self.fl_studio_version)
        if not self.reader.endswith(f"-v{self.schema_version}"):
            raise ValueError("Inventory reader and schema versions disagree")
        if self.schema_version == 2 and self.profile_id != (
            profile.identifier if profile else None
        ):
            raise ValueError("Inventory profile disagrees with exact declared version")
        if [e.event_index for e in self.events] != list(range(len(self.events))):
            raise ValueError("Event indices must be contiguous in file order")
        if self.coverage == "decoded" and self.diagnostics:
            raise ValueError("Incomplete evidence cannot claim decoded coverage")
        for event in self.events:
            if self.schema_version == 2:
                if event.header_hex is None:
                    raise ValueError("Inventory v2 requires retained event headers")
                header = bytes.fromhex(event.header_hex)
                if (
                    not header
                    or header[0] != event.event_id
                    or len(header) != event.payload_offset - event.file_offset
                ):
                    raise ValueError("Event header disagrees with ID or source offsets")
                if event.event_id < 192:
                    expected_width = 1 if event.event_id < 64 else 2 if event.event_id < 128 else 4
                    expected_rule = "classic"
                    if event.event_id == 172 and profile == FL26_READ_PROFILE:
                        expected_width, expected_rule = 3, "fl26-event-172-3bytes"
                    if (
                        len(header) != 1
                        or event.payload_size != expected_width
                        or event.framing_rule != expected_rule
                    ):
                        raise ValueError("Event width/rule differs from selected profile")
                    if event.scalar_hex is None:
                        raise ValueError("Scalar events require retained bytes")
                else:
                    prefix = header[1:]
                    if (
                        not prefix
                        or len(prefix) > 5
                        or prefix[-1] & 128
                        or any(value < 128 for value in prefix[:-1])
                    ):
                        raise ValueError("Invalid retained variable-length prefix")
                    length = sum((value & 127) << (7 * slot) for slot, value in enumerate(prefix))
                    if (
                        length != event.payload_size
                        or length > 2147483647
                        or event.framing_rule != "classic"
                    ):
                        raise ValueError("Event prefix/rule differs from payload evidence")
            if event.scalar_hex is not None:
                raw = bytes.fromhex(event.scalar_hex)
                if (
                    len(raw) != event.payload_size
                    or hashlib.sha256(raw).hexdigest() != event.payload_sha256
                ):
                    raise ValueError("Scalar bytes disagree with source event")
        groups: tuple[tuple[Sequence[TemplateNoteRecord | TemplateClipRecord], int], ...] = (
            (self.notes, 224),
            (self.clips, 233),
        )
        for records, event_id in groups:
            for item in records:
                if item.event_index >= len(self.events):
                    raise ValueError("Record references a nonexistent event")
                event = self.events[item.event_index]
                size = item.record_size if isinstance(item, TemplateClipRecord) else 24
                if isinstance(item, TemplateClipRecord) and (
                    profile is None or item.record_size != profile.playlist_record_size
                ):
                    raise ValueError("Clip width differs from selected version profile")
                if (
                    event.event_id != event_id
                    or item.file_offset != event.payload_offset + item.record_index * size
                ):
                    raise ValueError("Record location disagrees with its source event")
                if isinstance(item, TemplateNoteRecord) and item.pattern_id != event.pattern_id:
                    raise ValueError("Note Pattern differs from event context")
            for event in self.events:
                if event.event_id != event_id:
                    continue
                selected = [item for item in records if item.event_index == event.event_index]
                if self.coverage == "decoded" or selected:
                    if [item.record_index for item in selected] != list(range(len(selected))):
                        raise ValueError("Record indices must be contiguous")
                    payload = b"".join(bytes.fromhex(item.raw_hex) for item in selected)
                    if (
                        len(payload) != event.payload_size
                        or hashlib.sha256(payload).hexdigest() != event.payload_sha256
                    ):
                        raise ValueError("Retained records disagree with event payload hash/size")
        for automation in self.automation:
            if automation.event_index >= len(self.events):
                raise ValueError("Automation references a nonexistent event")
            event = self.events[automation.event_index]
            raw = bytes.fromhex(automation.raw_hex)
            if (
                event.event_id != automation.event_id
                or len(raw) != event.payload_size
                or hashlib.sha256(raw).hexdigest() != event.payload_sha256
            ):
                raise ValueError("Automation disagrees with source event")
            expected_kind = {21: "channel_type", 223: "legacy", 227: "links", 234: "points"}.get(
                event.event_id
            )
            if automation.kind != expected_kind or (event.event_id == 21 and raw != b"\x05"):
                raise ValueError("Automation kind differs from event type")
            if automation.channel_id != event.channel_id:
                raise ValueError("Automation channel differs from event context")
            if event.event_id == 227 and len(raw) % 20 == 0:
                if b"".join(bytes.fromhex(link.raw_hex) for link in automation.links) != raw:
                    raise ValueError("Automation link records do not cover retained payload")
            elif automation.links:
                raise ValueError("Unexpected decoded automation links")
            count = (
                struct.unpack_from("<I", raw, 17)[0]
                if event.event_id == 234 and len(raw) >= 21
                else None
            )
            if count is not None and count <= (len(raw) - 21) // 24:
                expected = raw[21 : 21 + count * 24]
                if (
                    len(automation.points) != count
                    or b"".join(bytes.fromhex(point.raw_hex) for point in automation.points)
                    != expected
                ):
                    raise ValueError("Automation point records disagree with count/payload")
                if automation.tail_hex != raw[21 + count * 24 :].hex():
                    raise ValueError("Automation trailing bytes were not retained")
            elif automation.points or automation.tail_hex:
                raise ValueError("Unexpected decoded automation points or trailing bytes")
            nested: Sequence[AutomationLink | AutomationPoint] = (
                automation.links or automation.points
            )
            record_prefix, stride = (21, 24) if event.event_id == 234 else (0, 20)
            for slot, record in enumerate(nested):
                if (
                    record.event_index != event.event_index
                    or record.record_index != slot
                    or record.file_offset != event.payload_offset + record_prefix + slot * stride
                ):
                    raise ValueError("Automation record location differs from its event")
        if profile is not None:
            expected_automation = [
                event.event_index
                for event in self.events
                if event.event_id in {223, 227, 234}
                or (event.event_id == 21 and event.scalar_hex == "05")
            ]
            if [item.event_index for item in self.automation] != expected_automation:
                raise ValueError("Known automation events must all retain their evidence")
        return self
