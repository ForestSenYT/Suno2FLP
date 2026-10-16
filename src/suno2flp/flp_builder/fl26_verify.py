"""Independent framing/record checks, deliberately not the encoder or inventory scanner."""

import hashlib
import struct

from suno2flp.core.errors import FlpWriteError
from suno2flp.core.writer_models import Fl26Verification, Fl26WriteIntent
from suno2flp.flp_builder.writer_intent import validate_write_intent


def _events(raw: bytes) -> list[tuple[int, bytes, bytes]]:
    if (
        len(raw) < 22
        or raw[:4] != b"FLhd"
        or raw[14:18] != b"FLdt"
        or struct.unpack_from("<I", raw, 4)[0] != 6
        or struct.unpack_from("<I", raw, 18)[0] != len(raw) - 22
    ):
        raise ValueError("Invalid single-chunk FL26 framing")
    cursor, version = 22, False
    result = []
    while cursor < len(raw):
        start, kind = cursor, raw[cursor]
        cursor += 1
        if kind < 192:
            size = 1 if kind < 64 else 2 if kind < 128 else 4
            if kind == 172:
                if not version:
                    raise ValueError("Event 172 before version")
                size = 3
        else:
            size = 0
            for step in range(5):
                if cursor >= len(raw):
                    raise ValueError("Truncated length")
                byte = raw[cursor]
                cursor += 1
                if step == 4 and byte > 7:
                    raise ValueError("Oversized length")
                size |= (byte & 127) << (step * 7)
                if byte < 128:
                    break
            else:
                raise ValueError("Unterminated length")
        if cursor + size > len(raw):
            raise ValueError("Truncated payload")
        payload = raw[cursor : cursor + size]
        if kind == 199:
            if version or payload != b"26.1.7.5654\0":
                raise ValueError("Wrong/duplicate exact version")
            version = True
        cursor += size
        result.append((kind, raw[start:cursor], payload))
    if not version:
        raise ValueError("Missing exact version")
    return result


def verify_fl26_output(original: bytes, output: bytes, intent: Fl26WriteIntent) -> Fl26Verification:
    try:
        intent = validate_write_intent(original, intent)
        before, after = _events(original), _events(output)
        if original[:18] != output[:18] or len(before) != len(after):
            raise ValueError("Header/event count changed")
        inventory = intent.inspection.inventory
        assert inventory is not None
        reviews = {t.binding_index: t for t in intent.policy.config.targets}
        expected_notes = {
            inventory.notes[reviews[p.binding_index].note_index].event_index: p
            for p in intent.binding_check.parts
        }
        expected_clips = {
            reviews[p.binding_index].clip_index: p for p in intent.binding_check.parts
        }
        changes = []
        preserved = {}
        note_count = clip_count = 0
        for index, ((old_id, old_event, old), (kind, new_event, payload)) in enumerate(
            zip(before, after, strict=True)
        ):
            if old_id != kind:
                raise ValueError("Event order/identity changed")
            if payload == old and old_event != new_event:
                raise ValueError("Unchanged payload length/header was normalized")
            if payload != old and kind >= 192:
                size = len(payload)
                prefix = []
                while size >= 128:
                    prefix.append((size & 127) | 128)
                    size //= 128
                canonical = bytes([kind, *prefix, size])
                if new_event[: len(new_event) - len(payload)] != canonical:
                    raise ValueError("Changed event length prefix is not canonical")
            if old_event != new_event:
                changes.append(index)
            if index not in intent.edit_event_indices:
                if old_event != new_event:
                    raise ValueError("Untargeted event bytes changed")
                preserved[index] = hashlib.sha256(old_event).hexdigest()
                continue
            if kind == 156:
                if len(payload) != 4 or int.from_bytes(payload, "little") != intent.tempo_millibpm:
                    raise ValueError("Tempo differs from intent")
            elif kind == 224:
                part = expected_notes[index]
                assert part.notes is not None
                if len(payload) != len(part.notes) * 24:
                    raise ValueError("Extra/missing note records")
                prototype = bytes.fromhex(
                    inventory.notes[reviews[part.binding_index].note_index].raw_hex
                )
                for slot, note in enumerate(part.notes):
                    record = payload[slot * 24 : (slot + 1) * 24]
                    if (
                        struct.unpack_from("<i", record)[0] != note.start_tick
                        or struct.unpack_from("<i", record, 8)[0] != note.duration_ticks
                        or record[6] != part.binding.template_channel_id
                        or record[12] != note.pitch
                        or record[21] != note.velocity
                    ):
                        raise ValueError("Note timing/pitch/channel/velocity differs")
                    if (
                        record[4:6] != prototype[4:6]
                        or record[7:8] != prototype[7:8]
                        or record[13:21] != prototype[13:21]
                        or record[22:24] != prototype[22:24]
                    ):
                        raise ValueError("Prototype note attributes changed")
                note_count += len(part.notes)
            elif kind == 233:
                if len(payload) != len(inventory.clips) * 88:
                    raise ValueError("Extra/missing clip records")
                for slot, clip in enumerate(inventory.clips):
                    record = payload[slot * 88 : (slot + 1) * 88]
                    part = expected_clips[slot]
                    prototype = bytes.fromhex(clip.raw_hex)
                    if (
                        struct.unpack_from("<i", record)[0] != 0
                        or struct.unpack_from("<i", record, 8)[0] != part.clip_length_ticks
                    ):
                        raise ValueError("Clip timing differs")
                    if record[4:8] != prototype[4:8] or record[12:] != prototype[12:]:
                        raise ValueError("Clip identity/crops/extension changed")
                clip_count += len(inventory.clips)
            else:
                raise ValueError("Edit budget contains unsupported event")
        if not set(changes) <= set(intent.edit_event_indices):
            raise ValueError("Changed-event budget exceeded")
        return Fl26Verification(
            template_sha256=hashlib.sha256(original).hexdigest(),
            output_sha256=hashlib.sha256(output).hexdigest(),
            note_count=note_count,
            clip_count=clip_count,
            changed_event_indices=changes,
            preserved_event_sha256=preserved,
        )
    except (ValueError, KeyError, IndexError, struct.error) as exc:
        raise FlpWriteError("writer_round_trip_failed", str(exc)) from exc
