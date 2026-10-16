"""Original narrow encoder: only explicitly authorized note/clip/tempo payloads change."""

import struct

from suno2flp.core.errors import FlpWriteError
from suno2flp.core.writer_models import Fl26WriteIntent
from suno2flp.flp_builder.writer_intent import validate_write_intent


def _length_prefix(size: int) -> bytes:
    if not 0 <= size <= 2147483647:
        raise FlpWriteError("writer_length_range", "Event length exceeds signed 32-bit range")
    result = bytearray()
    while size >= 128:
        result.append((size & 127) | 128)
        size >>= 7
    return bytes(result) + bytes([size])


def encode_fl26(raw: bytes, intent: Fl26WriteIntent) -> bytes:
    intent = validate_write_intent(raw, intent)
    inventory = intent.inspection.inventory
    assert inventory is not None and intent.tempo_millibpm is not None
    replacements: dict[int, bytes] = {}
    clips = [bytes.fromhex(c.raw_hex) for c in inventory.clips]
    reviews = {t.binding_index: t for t in intent.policy.config.targets}
    for part in intent.binding_check.parts:
        review = reviews[part.binding_index]
        prototype = inventory.notes[review.note_index]
        assert part.notes is not None and part.clip_length_ticks is not None
        payload = bytearray()
        for note in part.notes:
            record = bytearray.fromhex(prototype.raw_hex)
            struct.pack_into("<i", record, 0, note.start_tick)
            struct.pack_into("<i", record, 8, note.duration_ticks)
            record[6], record[12], record[21] = (
                part.binding.template_channel_id,
                note.pitch,
                note.velocity,
            )
            payload.extend(record)
        replacements[prototype.event_index] = bytes(payload)
        clip = bytearray(clips[review.clip_index])
        struct.pack_into("<i", clip, 0, 0)
        struct.pack_into("<i", clip, 8, part.clip_length_ticks)
        clips[review.clip_index] = bytes(clip)
    playlist = next(e for e in inventory.events if e.event_id == 233)
    replacements[playlist.event_index] = b"".join(clips)
    fine = next(e for e in inventory.events if e.event_id == 156)
    replacements[fine.event_index] = struct.pack("<I", intent.tempo_millibpm)
    output = bytearray()
    for event in inventory.events:
        old_payload = raw[event.payload_offset : event.payload_offset + event.payload_size]
        replacement = replacements.get(event.event_index, old_payload)
        if replacement == old_payload:
            output.extend(raw[event.file_offset : event.payload_offset + event.payload_size])
        elif event.event_id < 192:
            output.extend(raw[event.file_offset : event.payload_offset])
            output.extend(replacement)
        else:
            output.extend(bytes([event.event_id]) + _length_prefix(len(replacement)) + replacement)
    if len(output) > 0xFFFFFFFF:
        raise FlpWriteError("writer_length_range", "FLdt exceeds uint32 length")
    return raw[:18] + struct.pack("<I", len(output)) + bytes(output)
