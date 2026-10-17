"""Independent complete byte-budget checks; does not call the encoder."""

import struct

from suno2flp.core.audio_flp import DRUM_PREVIEW_KEYS, AudioPreviewPlan
from suno2flp.flp_builder.audio_profile import AudioComponents, payload, record
from suno2flp.integrations.template_inventory import scan_template_inventory


def verify_audio_preview(raw: bytes, profile: AudioComponents, plan: AudioPreviewPlan) -> None:
    plan = AudioPreviewPlan.model_validate(plan.model_dump())
    if len(raw) > 4 * 1024**2:
        raise ValueError("Candidate exceeds the bounded preview profile")
    inv = scan_template_inventory(raw)
    for e in inv.events:
        if e.event_id >= 192:
            groups = max(1, (e.payload_size.bit_length() + 6) // 7)
            length = bytes(
                ((e.payload_size >> (7 * j)) & 127) | (128 if j < groups - 1 else 0)
                for j in range(groups)
            )
            if raw[e.file_offset : e.payload_offset] != bytes([e.event_id]) + length:
                raise ValueError("Noncanonical candidate event header")
        if (e.event_id == 224 and e.payload_size != 24 * len(plan.notes)) or (
            e.event_id == 233 and e.payload_size != 88
        ):
            raise ValueError("Retain complete selected record payloads")
    header = bytearray(profile.base[:18])
    header[10:14] = struct.pack("<HH", 12, 960)
    if raw[:18] != bytes(header) or len(raw) != 22 + int.from_bytes(raw[18:22], "little"):
        raise ValueError("Candidate header/framing changed")
    insertion = profile.synth[0].event_index
    reference_ids = [e.event_id for e in profile.inventory.events]
    expected_ids = (
        reference_ids[:insertion]
        + [e.event_id for e in profile.synth] * 3
        + [e.event_id for e in profile.sample] * 9
        + reference_ids[insertion + len(profile.synth) :]
    )
    if [e.event_id for e in inv.events] != expected_ids:
        raise ValueError("Complete event order differs from the assessed reference scope")
    starts = [j for j, e in enumerate(inv.events) if e.event_id == 64]
    if (
        len(starts) != 12
        or inv.ppq != 960
        or inv.channel_count != 12
        or len(inv.notes) != len(plan.notes)
        or len(inv.clips) != 1
    ):
        raise ValueError("Candidate channel/note/clip coverage changed")
    selected = set()
    for channel, start in enumerate(starts):
        source, block = (
            (profile.base, profile.synth) if channel < 3 else (profile.sampler, profile.sample)
        )
        actual = inv.events[start : start + len(block)]
        if len(actual) != len(block):
            raise ValueError("Truncated channel")
        for e, reference_event in zip(actual, block, strict=True):
            selected.add(e.event_index)
            if e.event_id != reference_event.event_id:
                raise ValueError("Channel event scope changed")
            a, b = payload(raw, e), payload(source, reference_event)
            if e.event_id == 64:
                expected = struct.pack("<H", channel)
            elif e.event_id == 0:
                expected = b"\1"
            elif e.event_id == 219:
                expected = b[:4] + struct.pack("<I", 5000) + b[8:]
            elif e.event_id == 203:
                label = (
                    ("vocals", "bass", "other")[channel]
                    if channel < 3
                    else f"drum-{DRUM_PREVIEW_KEYS[channel - 3]}"
                )
                expected = (f"Suno2FLP {label}\0").encode("utf-16-le")
            elif e.event_id == 196:
                expected = (f"audio\\drum-{DRUM_PREVIEW_KEYS[channel - 3]}.wav\0").encode(
                    "utf-16-le"
                )
            else:
                expected = b
            if a != expected:
                raise ValueError("Channel payload differs from explicit budget")
    remaining = [e for e in inv.events if e.event_index not in selected]
    global_reference = [e for e in profile.inventory.events if e not in profile.synth]
    if len(remaining) != len(global_reference):
        raise ValueError("Unexpected/missing global events")
    for e, global_event in zip(remaining, global_reference, strict=True):
        if e.event_id != global_event.event_id:
            raise ValueError("Global event order changed")
        if e.event_id not in (224, 233) and record(raw, e) != record(profile.base, global_event):
            raise ValueError("Opaque/global bytes changed")
    source_order = sorted(
        plan.notes,
        key=lambda n: (n.start_tick, n.channel, n.source_part, n.source_occurrence),
    )
    for candidate_note, n in zip(inv.notes, source_order, strict=True):
        a = bytes.fromhex(candidate_note.raw_hex)
        b = bytes.fromhex(profile.inventory.notes[0].raw_hex)
        if (
            candidate_note.channel_id,
            candidate_note.pitch,
            candidate_note.position_ticks,
            candidate_note.length_ticks,
            candidate_note.velocity,
        ) != (n.channel, n.pitch, n.start_tick, n.end_tick - n.start_tick, 96):
            raise ValueError("Missing or altered source occurrence")
        if any(a[j] != b[j] for j in range(24) if j not in {*range(0, 4), 6, 7, *range(8, 14), 21}):
            raise ValueError("Unassessed note attributes changed")
    clip = inv.clips[0]
    a = bytes.fromhex(clip.raw_hex)
    b = bytes.fromhex(profile.inventory.clips[0].raw_hex)
    if clip.length_ticks != plan.end_tick or a[24:32] != struct.pack("<II", 0, plan.end_tick):
        raise ValueError("Clip extent/crop changed")
    if any(a[j] != b[j] for j in range(88) if j not in {*range(8, 12), *range(24, 32)}):
        raise ValueError("Unassessed clip bytes changed")
